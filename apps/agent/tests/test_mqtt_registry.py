import asyncio
from types import SimpleNamespace

import pytest

from goodnight_agent.devices.mqtt import MqttDeviceGateway
from goodnight_agent.domain.models import DeviceAvailability


@pytest.mark.asyncio
async def test_mqtt_metadata_messages_update_device_registry() -> None:
    gateway = MqttDeviceGateway()
    gateway._loop = asyncio.get_running_loop()

    gateway._on_message(
        gateway._client,
        None,
        SimpleNamespace(
            topic="goodnight/mock-arm/availability",
            payload=b'{"status":"online"}',
        ),
    )
    gateway._on_message(
        gateway._client,
        None,
        SimpleNamespace(
            topic="goodnight/mock-arm/capabilities",
            payload=b'{"capabilities":["move_phone_to_dock","stop_all_motion"]}',
        ),
    )
    await asyncio.sleep(0)

    record = gateway._devices["mock-arm"]
    assert record.availability is DeviceAvailability.ONLINE
    assert record.capabilities_known is True
    assert record.capabilities == ["move_phone_to_dock", "stop_all_motion"]


@pytest.mark.asyncio
async def test_mqtt_disconnect_invalidates_cached_online_state() -> None:
    gateway = MqttDeviceGateway()
    gateway._route_availability("mock-arm", DeviceAvailability.ONLINE)

    gateway._mark_devices_unknown()

    assert gateway._devices["mock-arm"].availability is DeviceAvailability.UNKNOWN
    assert gateway._devices["mock-arm"].capabilities_known is False
