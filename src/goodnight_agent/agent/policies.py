from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from goodnight_agent.agent.world_state import WorldState
from goodnight_agent.domain.models import Action, PermissionMode, SafetyCheck, utc_now


@dataclass(slots=True)
class PermissionPolicy:
    defaults: dict[str, PermissionMode] = field(
        default_factory=lambda: {
            "move_phone_to_dock": PermissionMode.AUTOMATIC,
            "turn_off_light": PermissionMode.AUTOMATIC,
            "block_phone_screen": PermissionMode.ASK,
            "play_story": PermissionMode.ASK,
            "swing_toy": PermissionMode.ASK,
            "set_rgb_indicator": PermissionMode.AUTOMATIC,
            "set_led_mode": PermissionMode.AUTOMATIC,
            "pull_blanket": PermissionMode.FORBIDDEN,
        }
    )

    def mode_for(self, capability: str) -> PermissionMode:
        return self.defaults.get(capability, PermissionMode.FORBIDDEN)


@dataclass(slots=True)
class SafetyPolicy:
    observation_ttl: timedelta = timedelta(minutes=2)

    def check(self, action: Action, state: WorldState) -> SafetyCheck:
        observation_fresh = (
            state.last_observation_at is not None
            and utc_now() - state.last_observation_at <= self.observation_ttl
        )
        device_online = state.device_states.get(action.device_id) == "online"
        outside_restricted_zone = not state.person_in_restricted_zone
        no_conflicting_action = state.active_action_id in {None, action.action_id}

        checks = {
            "observation_fresh": observation_fresh,
            "device_online": device_online,
            "outside_restricted_zone": outside_restricted_zone,
            "no_conflicting_action": no_conflicting_action,
        }

        if action.device_id in state.device_capabilities:
            checks["capability_advertised"] = (
                action.capability in state.device_capabilities[action.device_id]
            )

        if action.capability == "move_phone_to_dock":
            checks["phone_in_operation_zone"] = state.phone_location == "operation_zone"
        elif action.capability == "turn_off_light":
            checks["light_is_on"] = state.light_on is True

        failed = [name for name, passed in checks.items() if not passed]
        return SafetyCheck(
            allowed=not failed,
            reason=None if not failed else f"安全条件未满足: {', '.join(failed)}",
            checks=checks,
        )
