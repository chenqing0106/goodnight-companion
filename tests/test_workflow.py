import asyncio

import pytest

from goodnight_agent.agent.workflow import SimpleWorkflow
from goodnight_agent.devices.memory import InMemoryDeviceGateway
from goodnight_agent.devices.registry import DeviceRegistry, InMemoryDeviceRegistry
from goodnight_agent.domain.models import (
    ActionStatus,
    DeviceAvailability,
    DeviceRecord,
    Observation,
)
from goodnight_agent.infrastructure.events import InMemoryEventPublisher
from goodnight_agent.infrastructure.repositories import InMemoryActionRepository


def sleeping_observation(*, online: bool = True) -> Observation:
    return Observation(
        source="test",
        facts={
            "person_in_bed": True,
            "person_motion": "still",
            "stable_for_seconds": 960,
            "phone_location": "operation_zone",
            "light_on": True,
            "sleep_window": True,
            "device_states": {"mock-arm": "online" if online else "offline"},
        },
    )


def build_workflow(
    gateway: InMemoryDeviceGateway | None = None,
    *,
    registry: DeviceRegistry | None = None,
    timeout_ms: int = 500,
) -> tuple[SimpleWorkflow, InMemoryEventPublisher, InMemoryActionRepository]:
    events = InMemoryEventPublisher()
    actions = InMemoryActionRepository()
    workflow = SimpleWorkflow(
        gateway=gateway or InMemoryDeviceGateway(step_delay=0),
        registry=registry,
        publisher=events,
        actions=actions,
        command_timeout_ms=timeout_ms,
    )
    return workflow, events, actions


@pytest.mark.asyncio
async def test_sleep_cleanup_happy_path_verifies_real_world_results() -> None:
    workflow, events, _ = build_workflow()

    result = await workflow.process_observation(sleeping_observation())

    assert [action.capability for action in result.actions] == [
        "move_phone_to_dock",
        "turn_off_light",
    ]
    assert all(action.status is ActionStatus.SUCCEEDED for action in result.actions)
    assert workflow.world_state.phone_location == "dock"
    assert workflow.world_state.light_on is False
    assert [event.event_type for event in events.events].count("action.succeeded") == 2


@pytest.mark.asyncio
async def test_one_device_failure_does_not_cancel_independent_action() -> None:
    gateway = InMemoryDeviceGateway(step_delay=0, fail_capabilities={"move_phone_to_dock"})
    workflow, _, _ = build_workflow(gateway)

    result = await workflow.process_observation(sleeping_observation())

    assert result.actions[0].status is ActionStatus.FAILED
    assert result.actions[0].error_code == "SIMULATED_FAILURE"
    assert result.actions[1].status is ActionStatus.SUCCEEDED
    assert workflow.world_state.light_on is False


@pytest.mark.asyncio
async def test_safety_policy_blocks_offline_device() -> None:
    workflow, events, _ = build_workflow()

    result = await workflow.process_observation(sleeping_observation(online=False))

    assert all(action.status is ActionStatus.FAILED for action in result.actions)
    assert all(action.error_code == "SAFETY_CHECK_FAILED" for action in result.actions)
    safety_events = [event for event in events.events if event.event_type == "safety.checked"]
    assert safety_events[0].payload["checks"]["device_online"] is False


@pytest.mark.asyncio
async def test_user_can_stop_executing_physical_action() -> None:
    gateway = InMemoryDeviceGateway(step_delay=0.1)
    workflow, events, actions = build_workflow(gateway, timeout_ms=1_000)
    processing = asyncio.create_task(workflow.process_observation(sleeping_observation()))

    action_id = None
    for _ in range(100):
        running = [
            action for action in await actions.list() if action.status is ActionStatus.EXECUTING
        ]
        if running:
            action_id = running[0].action_id
            break
        await asyncio.sleep(0.005)
    assert action_id is not None

    await workflow.stop(action_id)
    result = await processing

    assert result.actions[0].status is ActionStatus.STOPPED
    assert any(event.event_type == "action.stop_requested" for event in events.events)
    assert any(event.event_type == "action.stopped" for event in events.events)


@pytest.mark.asyncio
async def test_device_timeout_becomes_explicit_failure() -> None:
    gateway = InMemoryDeviceGateway(step_delay=0, timeout_capabilities={"move_phone_to_dock"})
    workflow, _, _ = build_workflow(gateway, timeout_ms=20)

    result = await workflow.process_observation(sleeping_observation())

    assert result.actions[0].status is ActionStatus.FAILED
    assert result.actions[0].error_code in {"DEVICE_TIMEOUT", "DEVICE_STREAM_ENDED"}
    assert result.actions[1].status is ActionStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_registry_offline_state_overrides_observation_claim() -> None:
    registry = InMemoryDeviceRegistry(
        devices={
            "mock-arm": DeviceRecord(
                device_id="mock-arm",
                availability=DeviceAvailability.OFFLINE,
                capabilities=["move_phone_to_dock", "turn_off_light"],
                capabilities_known=True,
            )
        }
    )
    workflow, events, _ = build_workflow(registry=registry)

    result = await workflow.process_observation(sleeping_observation(online=True))

    assert all(action.status is ActionStatus.FAILED for action in result.actions)
    assert workflow.world_state.device_states["mock-arm"] == "offline"
    assert any(event.event_type == "device.registry_synced" for event in events.events)


@pytest.mark.asyncio
async def test_registry_blocks_capability_not_advertised_by_device() -> None:
    registry = InMemoryDeviceRegistry(
        devices={
            "mock-arm": DeviceRecord(
                device_id="mock-arm",
                availability=DeviceAvailability.ONLINE,
                capabilities=["turn_off_light"],
                capabilities_known=True,
            )
        }
    )
    workflow, _, _ = build_workflow(registry=registry)

    result = await workflow.process_observation(sleeping_observation())

    assert result.actions[0].status is ActionStatus.FAILED
    assert "capability_advertised" in (result.actions[0].reason or "")
    assert result.actions[1].status is ActionStatus.SUCCEEDED
