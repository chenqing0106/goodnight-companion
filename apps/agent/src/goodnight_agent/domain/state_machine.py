from __future__ import annotations

from dataclasses import dataclass

from goodnight_agent.domain.models import Action, ActionStatus, utc_now


class InvalidTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PENDING: {ActionStatus.EVALUATING, ActionStatus.SKIPPED},
    ActionStatus.EVALUATING: {ActionStatus.CHECKING, ActionStatus.SKIPPED},
    ActionStatus.CHECKING: {
        ActionStatus.WAITING_CONFIRMATION,
        ActionStatus.EXECUTING,
        ActionStatus.FAILED,
        ActionStatus.SKIPPED,
    },
    ActionStatus.WAITING_CONFIRMATION: {
        ActionStatus.EXECUTING,
        ActionStatus.FAILED,
        ActionStatus.STOPPED,
    },
    ActionStatus.EXECUTING: {
        ActionStatus.VERIFYING,
        ActionStatus.FAILED,
        ActionStatus.STOPPED,
    },
    ActionStatus.VERIFYING: {
        ActionStatus.SUCCEEDED,
        ActionStatus.FAILED,
        ActionStatus.STOPPED,
    },
    ActionStatus.SUCCEEDED: set(),
    ActionStatus.FAILED: set(),
    ActionStatus.STOPPED: set(),
    ActionStatus.SKIPPED: set(),
}


@dataclass(slots=True)
class ActionStateMachine:
    def transition(
        self,
        action: Action,
        target: ActionStatus,
        *,
        reason: str | None = None,
        error_code: str | None = None,
    ) -> Action:
        allowed = ALLOWED_TRANSITIONS[action.status]
        if target not in allowed:
            raise InvalidTransition(f"cannot transition {action.status} -> {target}")

        return action.model_copy(
            update={
                "status": target,
                "reason": reason if reason is not None else action.reason,
                "error_code": error_code,
                "updated_at": utc_now(),
            }
        )
