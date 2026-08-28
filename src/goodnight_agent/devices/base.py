from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from goodnight_agent.domain.models import DeviceCommand, DeviceStatus, SensorReading


class DeviceGateway(Protocol):
    def execute(self, command: DeviceCommand) -> AsyncIterator[DeviceStatus]: ...
    async def get_status(self, command_id: str) -> DeviceStatus | None: ...
    async def stop(self, command_id: str) -> None: ...
    async def close(self) -> None: ...


@runtime_checkable
class SensorGateway(Protocol):
    async def list_sensor_readings(self, device_id: str) -> list[SensorReading]: ...
