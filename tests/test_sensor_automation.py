from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from goodnight_agent.agent.scene_evaluator import SceneEvaluator
from goodnight_agent.agent.sensor_automation import VitalsSignalAutomation
from goodnight_agent.agent.workflow import SimpleWorkflow
from goodnight_agent.agent.world_state import WorldState
from goodnight_agent.domain.models import (
    DeviceAvailability,
    DeviceCommand,
    DeviceCommandStatus,
    DeviceRecord,
    DeviceStatus,
    SensorReading,
)
from goodnight_agent.infrastructure.events import InMemoryEventPublisher
from goodnight_agent.infrastructure.repositories import InMemoryActionRepository


class FakeEnvDevice:
    def __init__(self, *, online: bool = True) -> None:
        self.record = DeviceRecord(
            device_id="env-s3-01",
            availability=(DeviceAvailability.ONLINE if online else DeviceAvailability.OFFLINE),
            capabilities=["set_rgb_indicator", "set_led_mode"],
            capabilities_known=True,
        )
        self.commands: list[DeviceCommand] = []
        self.sensor_queue: asyncio.Queue[SensorReading] = asyncio.Queue()

    async def execute(self, command: DeviceCommand) -> AsyncIterator[DeviceStatus]:
        self.commands.append(command)
        mode = command.parameters["mode"]
        yield DeviceStatus(
            command_id=command.command_id,
            device_id=command.device_id,
            status=DeviceCommandStatus.SUCCEEDED,
            result={
                "actuator": "rgb",
                "command": mode,
                "state": "green" if mode == 2 else "off",
                "facts": {"rgb_indicator_mode": mode},
            },
        )

    async def get_status(self, command_id: str) -> DeviceStatus | None:
        return None

    async def stop(self, command_id: str) -> None:
        return None

    async def get_device(self, device_id: str) -> DeviceRecord | None:
        return self.record if device_id == self.record.device_id else None

    async def list_devices(self) -> list[DeviceRecord]:
        return [self.record]

    async def close(self) -> None:
        return None

    async def subscribe_sensor_readings(
        self,
        device_id: str,
    ) -> AsyncIterator[SensorReading]:
        while device_id == self.record.device_id:
            yield await self.sensor_queue.get()


def _reading(
    sensor: str,
    ts_ms: int,
    *,
    valid: bool,
    error: str | None = None,
) -> SensorReading:
    units = {"heart_rate": "bpm", "spo2": "%"}
    return SensorReading(
        device_id="env-s3-01",
        sensor=sensor,
        value=72 if sensor == "heart_rate" else 98,
        unit=units[sensor],
        valid=valid,
        error=error,
        ts_ms=ts_ms,
    )


def _build_automation(
    *, online: bool = True
) -> tuple[VitalsSignalAutomation, FakeEnvDevice, InMemoryEventPublisher]:
    gateway = FakeEnvDevice(online=online)
    events = InMemoryEventPublisher()
    workflow = SimpleWorkflow(
        gateway=gateway,
        registry=gateway,
        publisher=events,
        actions=InMemoryActionRepository(),
        evaluator=SceneEvaluator(device_id="env-s3-01"),
        command_timeout_ms=100,
    )
    automation = VitalsSignalAutomation(
        source=gateway,
        workflow=workflow,
        publisher=events,
        device_id="env-s3-01",
        required_samples=3,
        cooldown_seconds=0,
    )
    return automation, gateway, events


@pytest.mark.asyncio
async def test_three_valid_pairs_turn_rgb_green_once_and_record_trace() -> None:
    automation, gateway, events = _build_automation()

    for index in range(3):
        await automation.handle(_reading("heart_rate", index * 1_000, valid=True))
        await automation.handle(_reading("spo2", index * 1_000 + 1, valid=True))

    assert [(command.capability, command.parameters) for command in gateway.commands] == [
        ("set_rgb_indicator", {"mode": 2})
    ]
    assert automation.workflow.world_state.rgb_indicator_mode == 2
    event_types = [event.event_type for event in events.events]
    expected_order = [
        "condition.satisfied",
        "observation.updated",
        "decision.created",
        "tool.called",
        "action.progress",
        "action.succeeded",
    ]
    indices = [event_types.index(event_type) for event_type in expected_order]
    assert indices == sorted(indices)
    run_ids = {
        event.run_id for event in events.events if event.event_type in expected_order
    }
    assert len(run_ids) == 1

    await automation.handle(_reading("heart_rate", 4_000, valid=True))
    await automation.handle(_reading("spo2", 4_001, valid=True))
    assert len(gateway.commands) == 1


@pytest.mark.asyncio
async def test_finger_removed_after_stable_signal_turns_rgb_off() -> None:
    automation, gateway, _ = _build_automation()
    for index in range(3):
        await automation.handle(_reading("heart_rate", index * 1_000, valid=True))
        await automation.handle(_reading("spo2", index * 1_000 + 1, valid=True))
    for index in range(3, 6):
        await automation.handle(
            _reading(
                "heart_rate",
                index * 1_000,
                valid=False,
                error="finger_not_detected",
            )
        )
        await automation.handle(
            _reading(
                "spo2",
                index * 1_000 + 1,
                valid=False,
                error="finger_not_detected",
            )
        )

    assert [command.parameters["mode"] for command in gateway.commands] == [2, 0]


@pytest.mark.asyncio
async def test_offline_device_is_blocked_by_existing_safety_policy() -> None:
    automation, gateway, events = _build_automation(online=False)
    for index in range(3):
        await automation.handle(_reading("heart_rate", index * 1_000, valid=True))
        await automation.handle(_reading("spo2", index * 1_000 + 1, valid=True))

    assert gateway.commands == []
    failed = [event for event in events.events if event.event_type == "action.failed"]
    assert failed[-1].payload["status"] == "failed"


def test_satisfied_vitals_indicator_does_not_block_other_scenes() -> None:
    evaluator = SceneEvaluator(device_id="env-s3-01")
    state = WorldState(
        vitals_signal_state="stable",
        rgb_indicator_mode=2,
        person_in_bed=True,
        person_motion="still",
        stable_for_seconds=960,
        sleep_window=True,
        light_on=True,
    )

    decision = evaluator.evaluate(state)

    assert decision is not None
    assert decision.scene == "sleep_cleanup"
