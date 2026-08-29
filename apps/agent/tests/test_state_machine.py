import pytest

from goodnight_agent.domain.models import Action, ActionStatus
from goodnight_agent.domain.state_machine import (
    ALLOWED_TRANSITIONS,
    ActionStateMachine,
    InvalidTransition,
)


def test_state_machine_allows_declared_path() -> None:
    machine = ActionStateMachine()
    action = Action(run_id="run_test", capability="turn_off_light", device_id="mock-arm")

    for status in (
        ActionStatus.EVALUATING,
        ActionStatus.CHECKING,
        ActionStatus.EXECUTING,
        ActionStatus.VERIFYING,
        ActionStatus.SUCCEEDED,
    ):
        action = machine.transition(action, status)

    assert action.status is ActionStatus.SUCCEEDED


def test_state_machine_rejects_shortcut_to_success() -> None:
    action = Action(run_id="run_test", capability="turn_off_light", device_id="mock-arm")

    with pytest.raises(InvalidTransition):
        ActionStateMachine().transition(action, ActionStatus.SUCCEEDED)


@pytest.mark.parametrize(
    ("source", "target"),
    [(source, target) for source, targets in ALLOWED_TRANSITIONS.items() for target in targets],
)
def test_every_declared_transition_is_executable(
    source: ActionStatus,
    target: ActionStatus,
) -> None:
    action = Action(
        run_id="run_test",
        capability="turn_off_light",
        device_id="mock-arm",
        status=source,
    )

    assert ActionStateMachine().transition(action, target).status is target
