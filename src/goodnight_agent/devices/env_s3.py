from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt

from goodnight_agent.domain.models import (
    DeviceAvailability,
    DeviceCommand,
    DeviceCommandStatus,
    DeviceRecord,
    DeviceStatus,
    SensorReading,
    new_id,
    utc_now,
)

_CAPABILITY_TO_ACTUATOR = {
    "set_rgb_indicator": ("rgb", frozenset({0, 1, 2, 3})),
    "set_led_mode": ("led", frozenset({0, 7, 8, 9})),
}
_SENSOR_UNITS = {
    "temp": "C",
    "humidity": "%RH",
    "light": "adc_count",
    "heart_rate": "bpm",
    "spo2": "%",
}

# 传感器 mock：硬件故障期间由后端在 MQTT 网关层注入模拟读数，
# 下游（/api/devices/:id/sensors、sensor_automation、world_state）完全无感。
# 开关：环境变量 GOODNIGHT_ENV_S3_MOCK_SENSORS=1（见 api/app.py 的构建函数）。
# 基准值: (base, unit, jitter_spread)。真实读数一旦恢复（freshness 窗口内
# 收到 MQTT sensor 消息），对应传感器自动停止注入，让位给真实数据。
_MOCK_SENSOR_BASELINES: dict[str, tuple[float, str, float]] = {
    "temp": (24.0, "C", 0.5),
    "humidity": (56.0, "%RH", 3.0),
    "light": (738.0, "adc_count", 40.0),
    "heart_rate": (68.0, "bpm", 5.0),
    "spo2": (98.0, "%", 1.0),
}
_MOCK_INTERVAL_S = 1.0
_REAL_READING_FRESH_S = 10.0


@dataclass
class _PendingCommand:
    command: DeviceCommand
    actuator: str
    expected_mode: int
    queue: asyncio.Queue[DeviceStatus] = field(default_factory=asyncio.Queue)
    stop_requested: bool = False


@dataclass
class EnvS3MqttGateway:
    """Adapter for the ENV-SENSING-S3 firmware MQTT application contract."""

    host: str = "218.11.5.249"
    port: int = 10317
    device_id: str = "env-s3-01"
    username: str | None = None
    password: str | None = None
    connect_timeout: float = 5
    registry_wait_timeout: float = 1
    mock_sensors: bool = False
    _client: mqtt.Client = field(init=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _connected: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _loop_started: bool = field(default=False, init=False)
    _device_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _sensor_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _device: DeviceRecord = field(init=False)
    _readings: dict[str, SensorReading] = field(default_factory=dict, init=False)
    _sensor_subscribers: set[asyncio.Queue[SensorReading]] = field(
        default_factory=set,
        init=False,
    )
    _actuator_states: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _actuator_locks: dict[str, asyncio.Lock] = field(default_factory=dict, init=False)
    _pending: dict[str, _PendingCommand] = field(default_factory=dict, init=False)
    _commands: dict[str, DeviceCommand] = field(default_factory=dict, init=False)
    _statuses: dict[str, DeviceStatus] = field(default_factory=dict, init=False)
    _mock_task: asyncio.Task[None] | None = field(default=None, init=False)
    _real_reading_at: dict[str, float] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._device = DeviceRecord(
            device_id=self.device_id,
            capabilities=list(_CAPABILITY_TO_ACTUATOR),
            capabilities_known=True,
        )
        if self.mock_sensors:
            # mock 模式下设备直接呈在线，否则 SafetyPolicy 的 device_online
            # 检查会卡住 vitals 链路（set_rgb_indicator 无法下发）。
            # 注意：此期间 admin 页看到的“设备在线”也是模拟态。
            self._device = self._device.model_copy(
                update={"availability": DeviceAvailability.ONLINE}
            )
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"goodnight-env-s3-{new_id('client')}",
        )
        if self.username:
            self._client.username_pw_set(self.username, self.password)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    async def connect(self) -> None:
        if self._connected.is_set():
            return
        async with self._connect_lock:
            if self._connected.is_set():
                return
            self._loop = asyncio.get_running_loop()
            if not self._loop_started:
                self._client.connect_async(self.host, self.port)
                self._client.loop_start()
                self._loop_started = True
            await asyncio.wait_for(self._connected.wait(), timeout=self.connect_timeout)
            if self.mock_sensors and self._mock_task is None:
                self._mock_task = asyncio.create_task(self._mock_sensor_loop())

    def _note_real_reading(self, sensor: str) -> None:
        self._real_reading_at[sensor] = time.monotonic()

    async def _mock_sensor_loop(self) -> None:
        while True:
            now = time.monotonic()
            ts_ms = int(now * 1000)
            for sensor, (base, unit, spread) in _MOCK_SENSOR_BASELINES.items():
                last_real = self._real_reading_at.get(sensor)
                if last_real is not None and now - last_real < _REAL_READING_FRESH_S:
                    continue  # 真实硬件已恢复该传感器，让位给真实数据
                self._store_reading(
                    SensorReading(
                        device_id=self.device_id,
                        sensor=sensor,  # type: ignore[arg-type]
                        value=round(base + random.uniform(-spread, spread), 1),
                        unit=unit,
                        valid=True,
                        ts_ms=ts_ms,
                        error=None,
                    )
                )
            await asyncio.sleep(_MOCK_INTERVAL_S)

    def _topic(self, suffix: str) -> str:
        return f"{self.device_id}/{suffix}"

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code != 0:
            return
        client.subscribe(self._topic("status"), qos=1)
        client.subscribe(self._topic("sensor/#"), qos=0)
        client.subscribe(self._topic("actuator/+/state"), qos=1)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._connected.set)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._connected.clear)
            self._loop.call_soon_threadsafe(self._set_availability, DeviceAvailability.UNKNOWN)

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        prefix = f"{self.device_id}/"
        if not message.topic.startswith(prefix) or self._loop is None:
            return
        suffix = message.topic[len(prefix) :]
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(payload, dict):
            return

        if suffix == "status":
            try:
                availability = DeviceAvailability(payload["state"])
            except (KeyError, TypeError, ValueError):
                return
            self._loop.call_soon_threadsafe(self._set_availability, availability)
            return

        if suffix.startswith("sensor/"):
            sensor = suffix.removeprefix("sensor/")
            reading = self._parse_sensor(sensor, payload)
            if reading is not None:
                self._loop.call_soon_threadsafe(self._note_real_reading, sensor)
                self._loop.call_soon_threadsafe(self._store_reading, reading)
            return

        parts = suffix.split("/")
        if len(parts) == 3 and parts[0] == "actuator" and parts[2] == "state":
            actuator = parts[1]
            if actuator in {"rgb", "led"}:
                self._loop.call_soon_threadsafe(self._route_actuator_state, actuator, payload)

    def _parse_sensor(self, sensor: str, payload: dict[str, Any]) -> SensorReading | None:
        expected_unit = _SENSOR_UNITS.get(sensor)
        if expected_unit is None or payload.get("unit") != expected_unit:
            return None
        try:
            return SensorReading(
                device_id=self.device_id,
                sensor=sensor,
                value=payload["value"],
                unit=payload["unit"],
                valid=payload["valid"],
                ts_ms=payload["ts_ms"],
                error=payload.get("error"),
            )
        except (KeyError, ValueError, TypeError):
            return None

    def _set_availability(self, availability: DeviceAvailability) -> None:
        if self.mock_sensors and availability is not DeviceAvailability.ONLINE:
            # mock 模式下真实硬件的 offline/unknown 不覆盖模拟在线状态
            availability = DeviceAvailability.ONLINE
        self._device = self._device.model_copy(
            update={"availability": availability, "updated_at": utc_now()}
        )
        if availability is DeviceAvailability.UNKNOWN:
            self._device_event.clear()
        else:
            self._device_event.set()

    def _store_reading(self, reading: SensorReading) -> None:
        self._readings[reading.sensor] = reading
        self._sensor_event.set()
        for queue in tuple(self._sensor_subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(reading)

    def _route_actuator_state(self, actuator: str, payload: dict[str, Any]) -> None:
        accepted = payload.get("accepted")
        if not isinstance(accepted, bool):
            return
        self._actuator_states[actuator] = dict(payload)
        pending = self._pending.get(actuator)
        if pending is None:
            return

        acknowledged_command = payload.get("command")
        expected_command = 0 if pending.stop_requested else pending.expected_mode
        if accepted and acknowledged_command != expected_command:
            return

        if pending.stop_requested and accepted:
            status = DeviceStatus(
                command_id=pending.command.command_id,
                device_id=self.device_id,
                status=DeviceCommandStatus.STOPPED,
                result={"actuator": actuator, "state": payload.get("state")},
                message="执行器已切换为关闭模式",
            )
        elif accepted:
            facts = {
                "rgb_indicator_mode" if actuator == "rgb" else "led_mode": acknowledged_command
            }
            status = DeviceStatus(
                command_id=pending.command.command_id,
                device_id=self.device_id,
                status=DeviceCommandStatus.SUCCEEDED,
                progress=1,
                result={
                    "actuator": actuator,
                    "command": acknowledged_command,
                    "state": payload.get("state"),
                    "facts": facts,
                },
            )
        else:
            status = DeviceStatus(
                command_id=pending.command.command_id,
                device_id=self.device_id,
                status=DeviceCommandStatus.FAILED,
                error_code="DEVICE_REJECTED",
                message=str(payload.get("reason") or "设备拒绝执行器命令"),
            )
        self._statuses[status.command_id] = status
        pending.queue.put_nowait(status)

    async def execute(self, command: DeviceCommand) -> AsyncIterator[DeviceStatus]:
        await self.connect()
        if command.device_id != self.device_id:
            raise ValueError(f"ENV-S3 gateway only controls {self.device_id}")
        try:
            actuator, allowed_modes = _CAPABILITY_TO_ACTUATOR[command.capability]
            mode = command.parameters["mode"]
        except KeyError as exc:
            raise ValueError(f"unsupported ENV-S3 command: {command.capability}") from exc
        if type(mode) is not int or mode not in allowed_modes:
            raise ValueError(f"invalid mode for {command.capability}: {mode!r}")

        existing = self._statuses.get(command.command_id)
        if existing is not None and existing.status.terminal:
            yield existing
            return

        if self.mock_sensors:
            # mock 模式：不下发 MQTT，直接回执成功并写入 facts，
            # 让 vitals 链路（set_rgb_indicator）在硬件故障时也能走完。
            status = DeviceStatus(
                command_id=command.command_id,
                device_id=self.device_id,
                status=DeviceCommandStatus.SUCCEEDED,
                progress=1,
                result={
                    "actuator": actuator,
                    "command": mode,
                    "state": "mocked",
                    "facts": {
                        "rgb_indicator_mode" if actuator == "rgb" else "led_mode": mode
                    },
                },
            )
            self._statuses[status.command_id] = status
            yield status
            return

        lock = self._actuator_locks.setdefault(actuator, asyncio.Lock())
        async with lock:
            existing = self._statuses.get(command.command_id)
            if existing is not None and existing.status.terminal:
                yield existing
                return
            pending = _PendingCommand(
                command=command,
                actuator=actuator,
                expected_mode=mode,
            )
            self._pending[actuator] = pending
            self._commands[command.command_id] = command
            info = self._client.publish(
                self._topic(f"actuator/{actuator}/set"),
                str(mode),
                qos=1,
                retain=False,
            )
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self._pending.pop(actuator, None)
                raise RuntimeError(f"MQTT publish failed with rc={info.rc}")

            try:
                status = await asyncio.wait_for(
                    pending.queue.get(), timeout=command.timeout_ms / 1000
                )
                yield status
            finally:
                if self._pending.get(actuator) is pending:
                    self._pending.pop(actuator, None)

    async def get_status(self, command_id: str) -> DeviceStatus | None:
        return self._statuses.get(command_id)

    async def get_device(self, device_id: str) -> DeviceRecord | None:
        await self.connect()
        if device_id != self.device_id:
            return None
        if self._device.availability is DeviceAvailability.UNKNOWN:
            try:
                await asyncio.wait_for(
                    self._device_event.wait(), timeout=self.registry_wait_timeout
                )
            except TimeoutError:
                pass
        return self._device

    async def list_devices(self) -> list[DeviceRecord]:
        await self.get_device(self.device_id)
        return [self._device]

    async def list_sensor_readings(self, device_id: str) -> list[SensorReading]:
        await self.connect()
        if device_id != self.device_id:
            return []
        if not self._readings:
            try:
                await asyncio.wait_for(
                    self._sensor_event.wait(), timeout=self.registry_wait_timeout
                )
            except TimeoutError:
                pass
        return list(self._readings.values())

    async def subscribe_sensor_readings(
        self,
        device_id: str,
    ) -> AsyncIterator[SensorReading]:
        if device_id != self.device_id:
            return
        await self.connect()
        queue: asyncio.Queue[SensorReading] = asyncio.Queue(maxsize=100)
        self._sensor_subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._sensor_subscribers.discard(queue)

    async def stop(self, command_id: str) -> None:
        command = self._commands.get(command_id)
        if command is None:
            return
        actuator, _ = _CAPABILITY_TO_ACTUATOR[command.capability]
        pending = self._pending.get(actuator)
        if pending is None or pending.command.command_id != command_id:
            return
        pending.stop_requested = True
        info = self._client.publish(
            self._topic(f"actuator/{actuator}/set"),
            "0",
            qos=1,
            retain=False,
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT stop publish failed with rc={info.rc}")

    async def close(self) -> None:
        if self._mock_task is not None:
            self._mock_task.cancel()
            self._mock_task = None
        self._client.disconnect()
        if self._loop_started:
            self._client.loop_stop()
            self._loop_started = False
        self._connected.clear()
