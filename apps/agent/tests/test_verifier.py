from goodnight_agent.agent.verifier import ResultVerifier
from goodnight_agent.agent.world_state import WorldState
from goodnight_agent.domain.models import Action


def test_env_s3_actuator_verification_requires_matching_hardware_ack() -> None:
    verifier = ResultVerifier()
    action = Action(
        run_id="run_env",
        capability="set_led_mode",
        device_id="env-s3-01",
        parameters={"mode": 3},
    )

    matching = verifier.verify(
        action,
        WorldState(),
        {"actuator": "led", "command": 3, "state": "marquee"},
    )
    stale = verifier.verify(
        action,
        WorldState(),
        {"actuator": "led", "command": 2, "state": "cool_breathe"},
    )

    assert matching.verified is True
    assert stale.verified is False
