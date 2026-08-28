from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from goodnight_agent.agent.world_state import WorldState
from goodnight_agent.domain.models import Action


@dataclass(slots=True)
class VerificationResult:
    verified: bool
    reason: str


@dataclass(slots=True)
class ResultVerifier:
    def verify(
        self,
        action: Action,
        state: WorldState,
        device_result: dict[str, Any] | None = None,
    ) -> VerificationResult:
        if action.capability == "move_phone_to_dock":
            verified = state.phone_location == "dock"
            reason = "手机已到达固定收纳位置" if verified else "未确认手机到达固定收纳位置"
            return VerificationResult(verified=verified, reason=reason)

        if action.capability == "turn_off_light":
            verified = state.light_on is False
            reason = "灯光已关闭" if verified else "未确认灯光关闭"
            return VerificationResult(verified=verified, reason=reason)

        expected_actuator = {
            "set_rgb_indicator": "rgb",
            "set_led_mode": "led",
        }.get(action.capability)
        if expected_actuator is not None:
            result = device_result or {}
            verified = (
                result.get("actuator") == expected_actuator
                and result.get("command") == action.parameters.get("mode")
            )
            reason = "设备已确认灯光模式" if verified else "设备回执与请求的灯光模式不一致"
            return VerificationResult(verified=verified, reason=reason)

        return VerificationResult(verified=False, reason="当前能力没有结果验证规则")
