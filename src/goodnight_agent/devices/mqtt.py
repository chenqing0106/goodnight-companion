from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt

from goodnight_agent.domain.models import DeviceCommand, DeviceStatus, new_id


@dataclass
class MqttDeviceGateway:
    host: str = "127.0.0.1"
    port: int = 1883
    base_topic: str = "goodnight"
    username: str | None = None
    password: str | None = None
    connect_timeout: float = 5
    _client: mqtt.Client = field(init=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _connected: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _queues: dict[str, asyncio.Queue[DeviceStatus]] = field(default_factory=dict, init=False)
    _statuses: dict[str, DeviceStatus] = field(default_factory=dict, init=False)
    _commands: dict[str, DeviceCommand] = field(default_factory=dict, init=False)

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
        self._loop = asyncio.get_running_loop()
        self._client.connect_async(self.host, self.port)
        self._client.loop_start()
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

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            status = DeviceStatus.model_validate(payload)
        except (ValueError, UnicodeDecodeError):
            return

        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._route_status, status)

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
        self._client.loop_stop()
        self._connected.clear()
