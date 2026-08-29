from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from goodnight_agent.devices.base import DeviceGateway
from goodnight_agent.domain.models import DeviceCommand, DeviceStatus


@dataclass
class CapabilityGatewayRouter:
    """Route device commands to different gateways by capability.

    Real hardware capabilities (for example ENV-S3 lighting) keep using the
    primary gateway, while simulated capabilities (for example the blanket
    puller) are served by an in-memory gateway. Both sides share the same
    DeviceGateway call shape, so the workflow cannot tell them apart.
    """

    default: DeviceGateway
    overrides: dict[str, DeviceGateway] = field(default_factory=dict)

    def _gateway_for(self, capability: str) -> DeviceGateway:
        return self.overrides.get(capability, self.default)

    def _gateways(self) -> list[DeviceGateway]:
        seen: dict[int, DeviceGateway] = {id(self.default): self.default}
        for gateway in self.overrides.values():
            seen.setdefault(id(gateway), gateway)
        return list(seen.values())

    async def execute(self, command: DeviceCommand) -> AsyncIterator[DeviceStatus]:
        gateway = self._gateway_for(command.capability)
        async for status in gateway.execute(command):
            yield status

    async def get_status(self, command_id: str) -> DeviceStatus | None:
        for gateway in self._gateways():
            status = await gateway.get_status(command_id)
            if status is not None:
                return status
        return None

    async def stop(self, command_id: str) -> None:
        for gateway in self._gateways():
            await gateway.stop(command_id)

    async def close(self) -> None:
        # The default gateway lifecycle is owned by the app services; the
        # router only closes the override gateways it introduced.
        for gateway in self._gateways():
            if gateway is not self.default:
                await gateway.close()
