import asyncio
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest

from goodnight_agent.devices.env_s3 import EnvS3MqttGateway
from goodnight_agent.domain.models import (
    DeviceAvailability,
    DeviceCommand,
    DeviceCommandStatus,
)


def _message(topic: str, payload: bytes) -> SimpleNamespace:
    return SimpleNamespace(topic=topic, payload=payload)


@pytest.mark.asyncio
async def test_env_s3_routes_status_and_sensor_envelope() -> None:
    gateway = EnvS3MqttGateway()
    gateway._loop = asyncio.get_running_loop()

    gateway._on_message(
        gateway._client,
        None,
        _message("env-s3-01/status", b'{"state":"online"}'),
    )
    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/sensor/temp",
            b'{"value":25.0,"unit":"C","valid":true,"ts_ms":123456}',
        ),
    )
    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/sensor/heart_rate",
            b'{"value":0,"unit":"bpm","valid":false,'
            b'"error":"finger_not_detected","ts_ms":123457}',
        ),
    )
    await asyncio.sleep(0)

    assert gateway._device.availability is DeviceAvailability.ONLINE
    assert gateway._device.capabilities == ["set_rgb_indicator", "set_led_mode"]
    assert gateway._readings["temp"].value == 25
    assert gateway._readings["heart_rate"].valid is False
    assert gateway._readings["heart_rate"].error == "finger_not_detected"


@pytest.mark.asyncio
async def test_env_s3_ignores_sensor_payload_with_wrong_unit() -> None:
    gateway = EnvS3MqttGateway()
    gateway._loop = asyncio.get_running_loop()

    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/sensor/light",
            b'{"value":300,"unit":"lux","valid":true,"ts_ms":10}',
        ),
    )
    await asyncio.sleep(0)

    assert "light" not in gateway._readings


@pytest.mark.asyncio
async def test_env_s3_sensor_subscriber_receives_new_reading() -> None:
    gateway = EnvS3MqttGateway()
    gateway._loop = asyncio.get_running_loop()
    gateway._connected.set()
    stream = gateway.subscribe_sensor_readings("env-s3-01")
    next_reading = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)

    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/sensor/spo2",
            b'{"value":98,"unit":"%","valid":true,"ts_ms":20}',
        ),
    )
    reading = await next_reading
    await stream.aclose()

    assert reading.sensor == "spo2"
    assert reading.value == 98


@pytest.mark.asyncio
async def test_env_s3_publishes_plain_text_and_waits_for_matching_ack() -> None:
    gateway = EnvS3MqttGateway()
    gateway._loop = asyncio.get_running_loop()
    gateway._connected.set()
    published: list[tuple[str, str, int, bool]] = []

    def publish(topic: str, payload: str, qos: int, retain: bool) -> SimpleNamespace:
        published.append((topic, payload, qos, retain))
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    gateway._client.publish = publish
    command = DeviceCommand(
        command_id="cmd_led",
        action_id="act_led",
        device_id="env-s3-01",
        capability="set_led_mode",
        parameters={"mode": 3},
        timeout_ms=500,
    )

    collecting = asyncio.create_task(_collect(gateway, command))
    await asyncio.sleep(0)
    assert published == [("env-s3-01/actuator/led/set", "3", 1, False)]

    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/actuator/led/state",
            b'{"accepted":true,"command":2,"state":"cool_breathe"}',
        ),
    )
    await asyncio.sleep(0)
    assert not collecting.done()

    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/actuator/led/state",
            b'{"accepted":true,"command":3,"state":"marquee"}',
        ),
    )
    statuses = await collecting

    assert statuses[-1].status is DeviceCommandStatus.SUCCEEDED
    assert statuses[-1].result == {
        "actuator": "led",
        "command": 3,
        "state": "marquee",
        "facts": {},
    }


@pytest.mark.asyncio
async def test_env_s3_stop_turns_off_active_actuator_and_waits_for_ack() -> None:
    gateway = EnvS3MqttGateway()
    gateway._loop = asyncio.get_running_loop()
    gateway._connected.set()
    published: list[tuple[str, str]] = []

    def publish(topic: str, payload: str, qos: int, retain: bool) -> SimpleNamespace:
        published.append((topic, payload))
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    gateway._client.publish = publish
    command = DeviceCommand(
        command_id="cmd_rgb",
        action_id="act_rgb",
        device_id="env-s3-01",
        capability="set_rgb_indicator",
        parameters={"mode": 1},
        timeout_ms=500,
    )

    collecting = asyncio.create_task(_collect(gateway, command))
    await asyncio.sleep(0)
    await gateway.stop("cmd_rgb")
    assert published[-1] == ("env-s3-01/actuator/rgb/set", "0")

    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/actuator/rgb/state",
            b'{"accepted":true,"command":0,"state":"off"}',
        ),
    )
    statuses = await collecting

    assert statuses[-1].status is DeviceCommandStatus.STOPPED


@pytest.mark.asyncio
async def test_env_s3_does_not_republish_concurrent_duplicate_command() -> None:
    gateway = EnvS3MqttGateway()
    gateway._loop = asyncio.get_running_loop()
    gateway._connected.set()
    published: list[tuple[str, str]] = []

    def publish(topic: str, payload: str, qos: int, retain: bool) -> SimpleNamespace:
        published.append((topic, payload))
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    gateway._client.publish = publish
    command = DeviceCommand(
        command_id="cmd_duplicate",
        action_id="act_duplicate",
        device_id="env-s3-01",
        capability="set_rgb_indicator",
        parameters={"mode": 2},
        timeout_ms=500,
    )

    first = asyncio.create_task(_collect(gateway, command))
    duplicate = asyncio.create_task(_collect(gateway, command))
    await asyncio.sleep(0)
    gateway._on_message(
        gateway._client,
        None,
        _message(
            "env-s3-01/actuator/rgb/state",
            b'{"accepted":true,"command":2,"state":"green"}',
        ),
    )
    first_statuses, duplicate_statuses = await asyncio.gather(first, duplicate)

    assert published == [("env-s3-01/actuator/rgb/set", "2")]
    assert first_statuses[-1] == duplicate_statuses[-1]


async def _collect(
    gateway: EnvS3MqttGateway,
    command: DeviceCommand,
):
    return [status async for status in gateway.execute(command)]
