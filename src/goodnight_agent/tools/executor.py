from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from goodnight_agent.devices.base import DeviceGateway
from goodnight_agent.domain.models import Action, DeviceCommand, DeviceStatus
from goodnight_agent.tools.models import ToolCall
from goodnight_agent.tools.registry import ToolRegistry


@dataclass(slots=True)
class ToolExecutor:
    registry: ToolRegistry
    gateway: DeviceGateway

    def validate_action(self, action: Action) -> dict[str, object]:
        return self.registry.validate_arguments(action.capability, action.parameters)

    def prepare_call(self, action: Action, tool_call_id: str) -> ToolCall:
        arguments = self.validate_action(action)
        return ToolCall(
            tool_call_id=tool_call_id,
            action_id=action.action_id,
            tool_name=action.capability,
            device_id=action.device_id,
            arguments=arguments,
        )

    async def execute(
        self,
        call: ToolCall,
        *,
        timeout_ms: int,
    ) -> AsyncIterator[DeviceStatus]:
        command = DeviceCommand(
            command_id=call.tool_call_id,
            action_id=call.action_id,
            device_id=call.device_id,
            capability=call.tool_name,
            parameters=call.arguments,
            timeout_ms=timeout_ms,
        )
        async for status in self.gateway.execute(command):
            yield status

    async def stop(self, tool_call_id: str) -> None:
        await self.gateway.stop(tool_call_id)
