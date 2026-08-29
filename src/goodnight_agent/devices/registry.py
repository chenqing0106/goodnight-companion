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
                        "set_rgb_indicator",
                        "set_led_mode",
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


@dataclass
class OverlayDeviceRegistry:
    """Combine a primary registry (often a live MQTT gateway) with local
    overlay records, so simulated devices stay addressable even when the
    primary registry only knows about real hardware."""

    primary: DeviceRegistry
    overlay: InMemoryDeviceRegistry

    async def get_device(self, device_id: str) -> DeviceRecord | None:
        record = await self.overlay.get_device(device_id)
        if record is not None:
            return record
        return await self.primary.get_device(device_id)

    async def list_devices(self) -> list[DeviceRecord]:
        records = await self.primary.list_devices()
        known = {record.device_id for record in records}
        return records + [
            record
            for record in await self.overlay.list_devices()
            if record.device_id not in known
        ]

    async def close(self) -> None:
        await self.overlay.close()
