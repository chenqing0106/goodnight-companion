from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from goodnight_agent.domain.models import DeviceAvailability, DeviceRecord, utc_now


class DeviceRegistry(Protocol):
    async def get_device(self, device_id: str) -> DeviceRecord | None: ...

    async def list_devices(self) -> list[DeviceRecord]: ...

    async def close(self) -> None: ...


@dataclass
class InMemoryDeviceRegistry:
    devices: dict[str, DeviceRecord] = field(default_factory=dict)

    @classmethod
    def with_mock_device(cls, device_id: str = "mock-arm") -> InMemoryDeviceRegistry:
        return cls(
            devices={
                device_id: DeviceRecord(
                    device_id=device_id,
                    availability=DeviceAvailability.ONLINE,
                    capabilities=[
                        "move_phone_to_dock",
                        "turn_off_light",
                        "stop_all_motion",
                    ],
                    capabilities_known=True,
                )
            }
        )

    async def get_device(self, device_id: str) -> DeviceRecord | None:
        return self.devices.get(device_id)

    async def list_devices(self) -> list[DeviceRecord]:
        return list(self.devices.values())

    async def update(
        self,
        device_id: str,
        *,
        availability: DeviceAvailability | None = None,
        capabilities: list[str] | None = None,
    ) -> DeviceRecord:
        current = self.devices.get(device_id) or DeviceRecord(device_id=device_id)
        updated = current.model_copy(
            update={
                "availability": availability or current.availability,
                "capabilities": capabilities if capabilities is not None else current.capabilities,
                "capabilities_known": (capabilities is not None or current.capabilities_known),
                "updated_at": utc_now(),
            }
        )
        self.devices[device_id] = updated
        return updated

    async def close(self) -> None:
        return None
