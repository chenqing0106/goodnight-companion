from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from goodnight_agent.domain.models import (
    DeviceAvailability,
    DeviceRecord,
    Observation,
    utc_now,
)


class WorldState(BaseModel):
    person_in_bed: bool | None = None
    person_motion: str = "unknown"
    stable_for_seconds: int = 0
    inferred_sleep_state: str = "unknown"
    person_in_restricted_zone: bool = False
    phone_location: str = "unknown"
    phone_being_used: bool | None = None
    light_on: bool | None = None
    sleep_window: bool = False
    device_states: dict[str, str] = Field(default_factory=dict)
    device_capabilities: dict[str, list[str]] = Field(default_factory=dict)
    active_action_id: str | None = None
    last_observation_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    def apply_observation(self, observation: Observation) -> None:
        known_fields = set(type(self).model_fields)
        for key, value in observation.facts.items():
            if key in known_fields and key not in {"updated_at", "last_observation_at"}:
                setattr(self, key, value)

        self.last_observation_at = observation.timestamp
        self.updated_at = utc_now()

    def apply_result_facts(self, facts: dict[str, Any]) -> None:
        self.apply_observation(Observation(source="device_result", facts=facts))

    def apply_device_record(self, device_id: str, record: DeviceRecord | None) -> None:
        if record is None:
            self.device_states[device_id] = DeviceAvailability.UNKNOWN
            self.device_capabilities[device_id] = []
        else:
            self.device_states[device_id] = record.availability
            self.device_capabilities[device_id] = (
                list(record.capabilities) if record.capabilities_known else []
            )
        self.updated_at = utc_now()
