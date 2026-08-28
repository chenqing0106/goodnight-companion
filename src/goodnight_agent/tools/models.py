from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from goodnight_agent.domain.models import new_id


class ToolRiskLevel(StrEnum):
    READ_ONLY = "read_only"
    PHYSICAL_LOW = "physical_low"
    PHYSICAL_HIGH = "physical_high"
    SAFETY_CONTROL = "safety_control"


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: ToolRiskLevel


class ToolCall(BaseModel):
    tool_call_id: str = Field(default_factory=lambda: new_id("tool"))
    action_id: str
    tool_name: str
    device_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
