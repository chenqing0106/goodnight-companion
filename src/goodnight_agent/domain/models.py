from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now().astimezone()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class ActionStatus(StrEnum):
    PENDING = "pending"
    EVALUATING = "evaluating"
    CHECKING = "checking"
    WAITING_CONFIRMATION = "waiting_confirmation"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    SKIPPED = "skipped"


class PermissionMode(StrEnum):
    AUTOMATIC = "automatic"
    ASK = "ask"
    FORBIDDEN = "forbidden"


class DeviceCommandStatus(StrEnum):
    ACCEPTED = "accepted"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.STOPPED}


class Observation(BaseModel):
    observation_id: str = Field(default_factory=lambda: new_id("obs"))
    source: str
    timestamp: datetime = Field(default_factory=utc_now)
    facts: dict[str, Any]
    confidence: float | None = Field(default=None, ge=0, le=1)


class ActionRequest(BaseModel):
    capability: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    device_id: str = "mock-arm"


class Decision(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    scene: str
    should_intervene: bool
    reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    confirmation: Literal["automatic", "countdown", "required"] = "automatic"
    proposed_actions: list[ActionRequest] = Field(default_factory=list)


class Action(BaseModel):
    action_id: str = Field(default_factory=lambda: new_id("act"))
    run_id: str
    capability: str
    device_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.PENDING
    reason: str | None = None
    error_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DeviceCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: new_id("cmd"))
    action_id: str
    device_id: str
    capability: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(default=30_000, gt=0)


class DeviceStatus(BaseModel):
    command_id: str
    device_id: str
    status: DeviceCommandStatus
    progress: float | None = Field(default=None, ge=0, le=1)
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: str
    timestamp: datetime = Field(default_factory=utc_now)
    run_id: str | None = None
    action_id: str | None = None
    command_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SafetyCheck(BaseModel):
    allowed: bool
    reason: str | None = None
    checks: dict[str, bool] = Field(default_factory=dict)
