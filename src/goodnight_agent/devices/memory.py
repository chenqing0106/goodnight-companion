from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from goodnight_agent.domain.models import (
    DeviceCommand,
    DeviceCommandStatus,
    DeviceStatus,
)


@dataclass
class InMemoryDeviceGateway:
    step_delay: float = 0.01
    fail_capabilities: set[str] = field(default_factory=set)
    timeout_capabilities: set[str] = field(default_factory=set)
    statuses: dict[str, DeviceStatus] = field(default_factory=dict)
    execution_count: dict[str, int] = field(default_factory=dict)
    _stop_events: dict[str, asyncio.Event] = field(default_factory=dict)

    async def _emit(self, status: DeviceStatus) -> DeviceStatus:
        self.statuses[status.command_id] = status
        return status

    async def execute(self, command: DeviceCommand) -> AsyncIterator[DeviceStatus]:
        existing = self.statuses.get(command.command_id)
        if existing is not None and existing.status.terminal:
            yield existing
            return

        self.execution_count[command.command_id] = (
            self.execution_count.get(command.command_id, 0) + 1
        )
        stop_event = self._stop_events.setdefault(command.command_id, asyncio.Event())

        yield await self._emit(
            DeviceStatus(
                command_id=command.command_id,
                device_id=command.device_id,
                status=DeviceCommandStatus.ACCEPTED,
                progress=0,
            )
        )

        await asyncio.sleep(self.step_delay)
        if stop_event.is_set():
            yield await self._stopped(command)
            return

        yield await self._emit(
            DeviceStatus(
                command_id=command.command_id,
                device_id=command.device_id,
                status=DeviceCommandStatus.EXECUTING,
                progress=0.5,
            )
        )

        if command.capability in self.timeout_capabilities:
            await asyncio.sleep(command.timeout_ms / 1000 + self.step_delay)
            return

        await asyncio.sleep(self.step_delay)
        if stop_event.is_set():
            yield await self._stopped(command)
            return

        if command.capability in self.fail_capabilities:
            yield await self._emit(
                DeviceStatus(
                    command_id=command.command_id,
                    device_id=command.device_id,
                    status=DeviceCommandStatus.FAILED,
                    error_code="SIMULATED_FAILURE",
                    message="模拟设备执行失败",
                )
            )
            return

        result_facts: dict[str, object] = {}
        if command.capability == "move_phone_to_dock":
            result_facts["phone_location"] = "dock"
        elif command.capability == "turn_off_light":
            result_facts["light_on"] = False
        elif command.capability == "turn_on_light":
            result_facts["light_on"] = True
        elif command.capability == "pull_blanket":
            result_facts["blanket_position"] = "pulled"
        elif command.capability == "reset_arm":
            result_facts["arm_state"] = "reset"

        actuator = None
        if command.capability == "set_rgb_indicator":
            actuator = "rgb"
            result_facts["rgb_indicator_mode"] = command.parameters["mode"]
        elif command.capability == "set_led_mode":
            actuator = "led"
            result_facts["led_mode"] = command.parameters["mode"]

        result: dict[str, object] = {"facts": result_facts}
        if actuator is not None:
            result.update(
                {
                    "actuator": actuator,
                    "command": command.parameters["mode"],
                }
            )

        yield await self._emit(
            DeviceStatus(
                command_id=command.command_id,
                device_id=command.device_id,
                status=DeviceCommandStatus.SUCCEEDED,
                progress=1,
                result=result,
            )
        )

    async def _stopped(self, command: DeviceCommand) -> DeviceStatus:
        return await self._emit(
            DeviceStatus(
                command_id=command.command_id,
                device_id=command.device_id,
                status=DeviceCommandStatus.STOPPED,
                message="设备动作已停止",
            )
        )

    async def get_status(self, command_id: str) -> DeviceStatus | None:
        return self.statuses.get(command_id)

    async def stop(self, command_id: str) -> None:
        self._stop_events.setdefault(command_id, asyncio.Event()).set()

    async def close(self) -> None:
        return None
