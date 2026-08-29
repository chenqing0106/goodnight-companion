from __future__ import annotations

import argparse
import asyncio

from goodnight_agent.agent.workflow import SimpleWorkflow
from goodnight_agent.devices.memory import InMemoryDeviceGateway
from goodnight_agent.devices.mqtt import MqttDeviceGateway
from goodnight_agent.domain.models import ActionStatus, DeviceCommand, Observation, new_id
from goodnight_agent.infrastructure.events import InMemoryEventPublisher
from goodnight_agent.infrastructure.repositories import InMemoryActionRepository


def sleeping_observation(*, device_online: bool = True) -> Observation:
    return Observation(
        source="scenario",
        facts={
            "person_in_bed": True,
            "person_motion": "still",
            "stable_for_seconds": 16 * 60,
            "inferred_sleep_state": "asleep",
            "phone_location": "operation_zone",
            "light_on": True,
            "sleep_window": True,
            "device_states": {"mock-arm": "online" if device_online else "offline"},
        },
    )


async def wait_for_executing(actions: InMemoryActionRepository) -> str:
    for _ in range(200):
        for action in await actions.list():
            if action.status is ActionStatus.EXECUTING:
                return action.action_id
        await asyncio.sleep(0.005)
    raise TimeoutError("没有等到执行中的动作")


async def duplicate_command_demo(gateway: InMemoryDeviceGateway) -> None:
    command = DeviceCommand(
        command_id=new_id("cmd"),
        action_id=new_id("act"),
        device_id="mock-arm",
        capability="turn_off_light",
    )
    first = [status async for status in gateway.execute(command)]
    second = [status async for status in gateway.execute(command)]
    print("首次状态:", " -> ".join(item.status for item in first))
    print("重复状态:", " -> ".join(item.status for item in second))
    print("实际执行次数:", gateway.execution_count[command.command_id])


async def main() -> None:
    parser = argparse.ArgumentParser(description="运行好梦鸟 Agent 验证场景")
    parser.add_argument(
        "scenario",
        choices=[
            "success",
            "device-failure",
            "user-stop",
            "device-timeout",
            "duplicate-command",
            "safety-block",
        ],
        nargs="?",
        default="success",
    )
    parser.add_argument("--transport", choices=["memory", "mqtt"], default="memory")
    args = parser.parse_args()

    if args.transport == "mqtt":
        gateway = MqttDeviceGateway()
    else:
        gateway = InMemoryDeviceGateway(step_delay=0.08)
    events = InMemoryEventPublisher()
    actions = InMemoryActionRepository()
    workflow = SimpleWorkflow(
        gateway=gateway,
        registry=gateway if isinstance(gateway, MqttDeviceGateway) else None,
        publisher=events,
        actions=actions,
        command_timeout_ms=250 if args.scenario == "device-timeout" else 3_000,
    )

    if args.scenario == "duplicate-command":
        if not isinstance(gateway, InMemoryDeviceGateway):
            raise SystemExit("duplicate-command 场景当前使用 memory transport")
        await duplicate_command_demo(gateway)
        return
    if isinstance(gateway, InMemoryDeviceGateway):
        if args.scenario == "device-failure":
            gateway.fail_capabilities.add("move_phone_to_dock")
        elif args.scenario == "device-timeout":
            gateway.timeout_capabilities.add("move_phone_to_dock")

    observation = sleeping_observation(device_online=args.scenario != "safety-block")
    task = asyncio.create_task(workflow.process_observation(observation))
    if args.scenario == "user-stop":
        action_id = await wait_for_executing(actions)
        await workflow.stop(action_id)
    result = await task

    print(f"运行: {result.run_id}")
    for action in result.actions:
        print(f"- {action.capability}: {action.status} ({action.reason or '无'})")
    print("最终状态:", workflow.world_state.model_dump_json())
    print("事件时间线:")
    for event in events.events:
        suffix = f" [{event.action_id}]" if event.action_id else ""
        print(f"- {event.event_type}{suffix}")
    await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
