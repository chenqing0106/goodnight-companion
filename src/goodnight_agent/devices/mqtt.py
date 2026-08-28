from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt

from goodnight_agent.domain.models import (
    DeviceAvailability,
    DeviceCommand,
    DeviceRecord,
    DeviceStatus,
    new_id,
    utc_now,
)


@dataclass
class MqttDeviceGateway:
    host: str = "127.0.0.1"
    port: int = 1883
    base_topic: str = "goodnight"
    username: str | None = None
    password: str | None = None
    connect_timeout: float = 5
    registry_wait_timeout: float = 1
    _client: mqtt.Client = field(init=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _connected: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _loop_started: bool = field(default=False, init=False)
    _queues: dict[str, asyncio.Queue[DeviceStatus]] = field(default_factory=dict, init=False)
    _statuses: dict[str, DeviceStatus] = field(default_factory=dict, init=False)
    _commands: dict[str, DeviceCommand] = field(default_factory=dict, init=False)
    _devices: dict[str, DeviceRecord] = field(default_factory=dict, init=False)
    _availability_events: dict[str, asyncio.Event] = field(default_factory=dict, init=False)
    _capability_events: dict[str, asyncio.Event] = field(default_factory=dict, init=False)
    _any_device_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    def __post_init__(self) -> None:
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"goodnight-agent-{new_id('client')}",
        )
        if self.username:
            self._client.username_pw_set(self.username, self.password)
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
        client.subscribe(f"{self.base_topic}/+/command/status", qos=1)
        client.subscribe(f"{self.base_topic}/+/availability", qos=1)
        client.subscribe(f"{self.base_topic}/+/capabilities", qos=1)
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
            self._loop.call_soon_threadsafe(self._mark_devices_unknown)

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        prefix = f"{self.base_topic}/"
        if not message.topic.startswith(prefix):
            return
        try:
            device_id, suffix = message.topic[len(prefix) :].split("/", 1)
            payload = json.loads(message.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return

        if self._loop is None:
            return

        if suffix == "availability":
            try:
                availability = DeviceAvailability(payload["status"])
            except (KeyError, ValueError, TypeError):
                return
            self._loop.call_soon_threadsafe(
                self._route_availability,
                device_id,
                availability,
            )
            return

        if suffix == "capabilities":
            capabilities = payload.get("capabilities")
            if not isinstance(capabilities, list) or not all(
                isinstance(item, str) for item in capabilities
            ):
                return
            self._loop.call_soon_threadsafe(
                self._route_capabilities,
                device_id,
                capabilities,
            )
            return

        if suffix != "command/status":
            return
        try:
            status = DeviceStatus.model_validate(payload)
        except ValueError:
            return
        self._loop.call_soon_threadsafe(self._route_status, status)

    def _route_availability(
        self,
        device_id: str,
        availability: DeviceAvailability,
    ) -> None:
        current = self._devices.get(device_id) or DeviceRecord(device_id=device_id)
        self._devices[device_id] = current.model_copy(
            update={"availability": availability, "updated_at": utc_now()}
        )
        self._availability_events.setdefault(device_id, asyncio.Event()).set()
        self._any_device_event.set()

    def _route_capabilities(self, device_id: str, capabilities: list[str]) -> None:
        current = self._devices.get(device_id) or DeviceRecord(device_id=device_id)
        self._devices[device_id] = current.model_copy(
            update={
                "capabilities": list(capabilities),
                "capabilities_known": True,
                "updated_at": utc_now(),
            }
        )
        self._capability_events.setdefault(device_id, asyncio.Event()).set()
        self._any_device_event.set()

    def _mark_devices_unknown(self) -> None:
        for device_id, current in tuple(self._devices.items()):
            self._devices[device_id] = current.model_copy(
                update={
                    "availability": DeviceAvailability.UNKNOWN,
                    "capabilities_known": False,
                    "updated_at": utc_now(),
                }
            )
        for event in self._availability_events.values():
            event.clear()
        for event in self._capability_events.values():
            event.clear()

    def _route_status(self, status: DeviceStatus) -> None:
        self._statuses[status.command_id] = status
        queue = self._queues.get(status.command_id)
        if queue is not None:
            queue.put_nowait(status)

    async def execute(self, command: DeviceCommand) -> AsyncIterator[DeviceStatus]:
        await self.connect()
        existing = self._statuses.get(command.command_id)
        if existing is not None and existing.status.terminal:
            yield existing
            return

        queue = self._queues.setdefault(command.command_id, asyncio.Queue())
        self._commands[command.command_id] = command
        topic = f"{self.base_topic}/{command.device_id}/command"
        info = self._client.publish(
            topic,
            command.model_dump_json(),
            qos=1,
            retain=False,
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with rc={info.rc}")

        try:
            while True:
                status = await asyncio.wait_for(queue.get(), timeout=command.timeout_ms / 1000)
                yield status
                if status.status.terminal:
                    return
        finally:
            self._queues.pop(command.command_id, None)

    async def get_status(self, command_id: str) -> DeviceStatus | None:
        return self._statuses.get(command_id)

    async def get_device(self, device_id: str) -> DeviceRecord | None:
        await self.connect()
        record = self._devices.get(device_id)
        if record is None or record.availability is DeviceAvailability.UNKNOWN:
            event = self._availability_events.setdefault(device_id, asyncio.Event())
            try:
                await asyncio.wait_for(event.wait(), timeout=self.registry_wait_timeout)
            except TimeoutError:
                return self._devices.get(device_id)

        record = self._devices.get(device_id)
        if (
            record is not None
            and record.availability is DeviceAvailability.ONLINE
            and not record.capabilities_known
        ):
            event = self._capability_events.setdefault(device_id, asyncio.Event())
            try:
                await asyncio.wait_for(event.wait(), timeout=self.registry_wait_timeout)
            except TimeoutError:
                pass
        return self._devices.get(device_id)

    async def list_devices(self) -> list[DeviceRecord]:
        await self.connect()
        if not self._devices:
            try:
                await asyncio.wait_for(
                    self._any_device_event.wait(),
                    timeout=self.registry_wait_timeout,
                )
            except TimeoutError:
                pass
        return list(self._devices.values())

    async def stop(self, command_id: str) -> None:
        original = self._commands.get(command_id)
        if original is None:
            return
        stop_command = DeviceCommand(
            action_id=original.action_id,
            device_id=original.device_id,
            capability="stop_all_motion",
            parameters={"target_command_id": command_id},
            timeout_ms=5_000,
        )
        topic = f"{self.base_topic}/{original.device_id}/command"
        self._client.publish(topic, stop_command.model_dump_json(), qos=1, retain=False)

    async def close(self) -> None:
        self._client.disconnect()
        if self._loop_started:
            self._client.loop_stop()
            self._loop_started = False
        self._connected.clear()
