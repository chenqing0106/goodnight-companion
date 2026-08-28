import pytest

from goodnight_agent.devices.memory import InMemoryDeviceGateway
from goodnight_agent.domain.models import Action, DeviceCommandStatus
from goodnight_agent.tools.executor import ToolExecutor
from goodnight_agent.tools.registry import (
    ToolArgumentsError,
    ToolNotFoundError,
    build_default_tool_registry,
)


def test_default_tool_registry_exposes_high_level_device_tools() -> None:
    registry = build_default_tool_registry()

    definitions = registry.list_definitions()

    assert [definition.name for definition in definitions] == [
        "move_phone_to_dock",
        "turn_off_light",
        "stop_all_motion",
    ]
    assert definitions[0].input_schema["properties"]["speed_profile"]["default"] == ("night_slow")


def test_tool_registry_validates_and_normalizes_arguments() -> None:
    registry = build_default_tool_registry()

    assert registry.validate_arguments("move_phone_to_dock", {}) == {"speed_profile": "night_slow"}

    with pytest.raises(ToolArgumentsError):
        registry.validate_arguments(
            "move_phone_to_dock",
            {"speed_profile": "unsafe_fast"},
        )
    with pytest.raises(ToolArgumentsError):
        registry.validate_arguments("turn_off_light", {"unexpected": True})
    with pytest.raises(ToolNotFoundError):
        registry.validate_arguments("unknown_tool", {})


@pytest.mark.asyncio
async def test_tool_executor_converts_validated_call_to_device_command() -> None:
    gateway = InMemoryDeviceGateway(step_delay=0)
    executor = ToolExecutor(
        registry=build_default_tool_registry(),
        gateway=gateway,
    )
    action = Action(
        run_id="run_test",
        capability="move_phone_to_dock",
        device_id="mock-arm",
    )

    call = executor.prepare_call(action, "cmd_stable")
    statuses = [status async for status in executor.execute(call, timeout_ms=500)]

    assert call.arguments == {"speed_profile": "night_slow"}
    assert statuses[-1].status is DeviceCommandStatus.SUCCEEDED
    assert gateway.execution_count["cmd_stable"] == 1
