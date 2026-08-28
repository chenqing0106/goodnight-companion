from __future__ import annotations

from dataclasses import dataclass

from goodnight_agent.agent.world_state import WorldState
from goodnight_agent.domain.models import ActionRequest, Decision


@dataclass(slots=True)
class SceneEvaluator:
    stable_sleep_seconds: int = 15 * 60
    device_id: str = "mock-arm"

    def evaluate(self, state: WorldState) -> Decision | None:
        asleep = (
            state.person_in_bed is True
            and state.person_motion == "still"
            and state.stable_for_seconds >= self.stable_sleep_seconds
            and state.sleep_window
        )
        if not asleep:
            return None

        actions: list[ActionRequest] = []
        if state.phone_location == "operation_zone":
            actions.append(
                ActionRequest(
                    capability="move_phone_to_dock",
                    device_id=self.device_id,
                    parameters={"speed_profile": "night_slow"},
                )
            )
        if state.light_on is True:
            actions.append(
                ActionRequest(
                    capability="turn_off_light",
                    device_id=self.device_id,
                )
            )

        if not actions:
            return Decision(
                scene="sleep_cleanup",
                should_intervene=False,
                reason="用户已稳定入睡，但没有需要处理的手机或灯光",
            )

        return Decision(
            scene="sleep_cleanup",
            should_intervene=True,
            reason="用户已稳定入睡，手机或灯光仍需处理",
            confidence=0.9,
            confirmation="automatic",
            proposed_actions=actions,
        )
