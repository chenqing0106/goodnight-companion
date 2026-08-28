from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from goodnight_agent.tools.models import ToolDefinition, ToolRiskLevel


class ToolError(ValueError):
    pass


class ToolNotFoundError(ToolError):
    pass


class ToolArgumentsError(ToolError):
    pass


class NoParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MovePhoneToDockParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed_profile: Literal["night_slow", "normal"] = "night_slow"


class StopAllMotionParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_command_id: str


class SetRgbIndicatorParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Annotated[int, Field(strict=True, ge=0, le=3)]


class SetLedModeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Annotated[int, Field(strict=True, ge=0, le=7)]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    definition: ToolDefinition
    parameters_model: type[BaseModel]


@dataclass
class ToolRegistry:
    _tools: dict[str, RegisteredTool] = field(default_factory=dict)

    def register(
        self,
        *,
        name: str,
        description: str,
        risk_level: ToolRiskLevel,
        parameters_model: type[BaseModel],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool {name} is already registered")
        definition = ToolDefinition(
            name=name,
            description=description,
            input_schema=parameters_model.model_json_schema(),
            risk_level=risk_level,
        )
        self._tools[name] = RegisteredTool(
            definition=definition,
            parameters_model=parameters_model,
        )

    def require(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"tool {name} is not registered") from exc

    def validate_arguments(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        registered = self.require(name)
        try:
            validated = registered.parameters_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolArgumentsError(f"invalid arguments for tool {name}: {exc}") from exc
        return validated.model_dump(mode="json", exclude_none=True)

    def list_definitions(self) -> list[ToolDefinition]:
        return [registered.definition for registered in self._tools.values()]


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        name="move_phone_to_dock",
        description="将操作区域内的手机移动到固定收纳位置",
        risk_level=ToolRiskLevel.PHYSICAL_LOW,
        parameters_model=MovePhoneToDockParameters,
    )
    registry.register(
        name="turn_off_light",
        description="关闭睡眠空间内已确认可控的灯光",
        risk_level=ToolRiskLevel.PHYSICAL_LOW,
        parameters_model=NoParameters,
    )
    registry.register(
        name="stop_all_motion",
        description="停止指定设备命令对应的所有运动",
        risk_level=ToolRiskLevel.SAFETY_CONTROL,
        parameters_model=StopAllMotionParameters,
    )
    registry.register(
        name="set_rgb_indicator",
        description="设置 ENV-S3 三色指示灯，0 熄灭、1 红色、2 绿色、3 蓝色",
        risk_level=ToolRiskLevel.PHYSICAL_LOW,
        parameters_model=SetRgbIndicatorParameters,
    )
    registry.register(
        name="set_led_mode",
        description="设置 ENV-S3 灯带模式，取值 0 到 7，0 表示熄灭",
        risk_level=ToolRiskLevel.PHYSICAL_LOW,
        parameters_model=SetLedModeParameters,
    )
    return registry
