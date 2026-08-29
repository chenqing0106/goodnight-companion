import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from goodnight_agent.api.app import create_app
from goodnight_agent.devices.memory import InMemoryDeviceGateway
from goodnight_agent.devices.registry import InMemoryDeviceRegistry
from goodnight_agent.domain.models import DeviceAvailability

EXPECTED_CLOCKS = [
    "07:30:01",
    "07:30:02",
    "07:30:02",
    "07:30:02",
    "07:30:03",
    "07:30:05",
    "07:31:05",
    "07:31:35",
    "07:31:38",
    "07:31:40",
]


async def _wait_for_thread_status(
    client: AsyncClient,
    run_id: str,
    *,
    timeout: float = 20,
) -> list[dict]:
    """Poll recent events until the scenario thread reaches a terminal state."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        events = (
            await client.get("/api/events/recent", params={"limit": 500})
        ).json()
        steps = [
            event
            for event in events
            if event["event_type"] == "activity.step" and event["run_id"] == run_id
        ]
        if steps and steps[-1]["payload"]["thread_status"] in {
            "completed",
            "failed",
            "stopped",
        }:
            return steps
        await asyncio.sleep(0.05)
    raise AssertionError("scenario did not reach a terminal state in time")


def _dedupe_steps(steps: list[dict]) -> list[dict]:
    """Keep the last update of each step_index, preserving first-seen order."""
    order: list[int] = []
    latest: dict[int, dict] = {}
    for step in steps:
        index = step["payload"]["step_index"]
        if index not in latest:
            order.append(index)
        latest[index] = step
    return [latest[index] for index in order]


@pytest.mark.asyncio
async def test_wake_up_blanket_completes_full_sequence() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/debug/mock-activity",
            json={"scenario": "wake_up_blanket", "speed": 4.0},
        )
        assert started.status_code == 200
        run_id = started.json()["run_id"]
        assert started.json()["scenario"] == "wake_up_blanket"
        assert started.json()["total_steps"] == len(EXPECTED_CLOCKS)

        steps = _dedupe_steps(await _wait_for_thread_status(client, run_id))
        actions = (await client.get("/api/actions")).json()
        state = (await client.get("/api/state")).json()
        status = (await client.get("/api/debug/mock-activity")).json()

    assert [step["payload"]["clock"] for step in steps] == EXPECTED_CLOCKS
    assert steps[-1]["payload"]["thread_status"] == "completed"
    assert steps[-1]["payload"]["subject"] == "渐进唤醒"

    checks_step = steps[2]["payload"]
    assert checks_step["kind"] == "checks"
    assert checks_step["checks"] == [
        "灯光设备在线",
        "机械臂安全区域有效",
        "被角位于预设操作位置",
        "用户未提出停止",
    ]
    plan_step = steps[3]["payload"]
    assert plan_step["kind"] == "plan"
    assert len(plan_step["plan"]) == 4

    # 每一步硬件动作都以真实回执为准，逐条可追溯。
    by_capability = {}
    for action in actions:
        by_capability.setdefault(action["capability"], []).append(action)
    assert [a["parameters"]["mode"] for a in by_capability["set_rgb_indicator"]] == [1, 2]
    assert [a["parameters"]["mode"] for a in by_capability["set_led_mode"]] == [7, 8]
    assert by_capability["turn_on_light"][0]["device_id"] == "sim-arm"
    assert by_capability["pull_blanket"][0]["device_id"] == "sim-arm"
    assert by_capability["reset_arm"][0]["device_id"] == "sim-arm"
    for capability, items in by_capability.items():
        assert all(a["status"] == "succeeded" for a in items), capability

    tool_steps = [step["payload"] for step in steps if step["payload"]["kind"] == "tool"]
    assert tool_steps
    for payload in tool_steps:
        assert payload["tool_status"] == "done"
        for tool in payload["tools"]:
            assert tool["status"] == "succeeded"
            assert tool["execution"] in {"real", "simulated"}
            assert tool["receipt"]

    assert state["rgb_indicator_mode"] == 2
    assert state["led_mode"] == 8
    assert state["light_on"] is True
    assert status == {"running": False, "run_id": None, "scenario": None}


@pytest.mark.asyncio
async def test_wake_up_blanket_rejects_duplicate_start() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/debug/mock-activity",
            json={"scenario": "wake_up_blanket", "speed": 1.0},
        )
        repeated = await client.post(
            "/api/debug/mock-activity",
            json={"scenario": "wake_up_blanket", "speed": 1.0},
        )
        status = (await client.get("/api/debug/mock-activity")).json()
        await client.post("/api/debug/mock-activity/stop")

    assert started.status_code == 200
    assert repeated.status_code == 409
    assert status["running"] is True
    assert status["scenario"] == "wake_up_blanket"


@pytest.mark.asyncio
async def test_wake_up_blanket_stop_resets_arm_and_allows_replay() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/debug/mock-activity",
            json={"scenario": "wake_up_blanket", "speed": 1.0},
        )
        run_id = started.json()["run_id"]
        await asyncio.sleep(1.2)

        stopped = await client.post("/api/debug/mock-activity/stop")
        assert stopped.status_code == 200
        assert stopped.json() == {"run_id": run_id, "status": "stopped"}

        steps = _dedupe_steps(await _wait_for_thread_status(client, run_id))
        actions = (await client.get("/api/actions")).json()

        # 停止后可以立即重新播放。
        replayed = await client.post(
            "/api/debug/mock-activity",
            json={"scenario": "wake_up_blanket", "speed": 4.0},
        )
        assert replayed.status_code == 200
        replay_steps = await _wait_for_thread_status(client, replayed.json()["run_id"])
        await client.post("/api/debug/mock-activity/stop")

    assert steps[-1]["payload"]["thread_status"] == "stopped"
    assert steps[-1]["payload"]["title"] == "已停止"
    # 停止之后没有继续播放剩余场景步骤。
    published_clocks = [
        step["payload"]["clock"] for step in steps[:-1] if step["payload"]["clock"]
    ]
    assert "07:31:40" not in published_clocks
    # 停止时仍然模拟机械臂复位，且复位有真实动作回执。
    reset_actions = [a for a in actions if a["capability"] == "reset_arm"]
    assert reset_actions
    assert reset_actions[-1]["status"] == "succeeded"
    assert _dedupe_steps(replay_steps)[-1]["payload"]["thread_status"] == "completed"


@pytest.mark.asyncio
async def test_wake_up_blanket_tool_failure_is_shown_as_failed() -> None:
    gateway = InMemoryDeviceGateway(step_delay=0, fail_capabilities={"set_rgb_indicator"})
    app = create_app(gateway)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/debug/mock-activity",
            json={"scenario": "wake_up_blanket", "speed": 4.0},
        )
        run_id = started.json()["run_id"]
        steps = _dedupe_steps(await _wait_for_thread_status(client, run_id))
        actions = (await client.get("/api/actions")).json()
        state = (await client.get("/api/state")).json()

    final = steps[-1]["payload"]
    assert final["thread_status"] == "failed"
    assert "没有完成" in final["detail"]
    assert final["kind"] == "tool"
    assert final["tools"][0]["name"] == "set_rgb_indicator"
    assert final["tools"][0]["status"] == "failed"
    # 失败步骤之后的场景步骤没有继续播放。
    assert [step["payload"]["clock"] for step in steps] == EXPECTED_CLOCKS[:5]
    rgb_actions = [a for a in actions if a["capability"] == "set_rgb_indicator"]
    assert len(rgb_actions) == 1
    assert rgb_actions[0]["status"] == "failed"
    # 失败不会被显示成成功：灯光没有进入完成状态。
    assert state["rgb_indicator_mode"] != 2
    assert not any(a["capability"] == "pull_blanket" for a in actions)


@pytest.mark.asyncio
async def test_wake_up_blanket_device_offline_fails_safety_check() -> None:
    registry = InMemoryDeviceRegistry.with_mock_device("mock-arm")
    await registry.update("mock-arm", availability=DeviceAvailability.OFFLINE)
    app = create_app(InMemoryDeviceGateway(step_delay=0), registry)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/debug/mock-activity",
            json={"scenario": "wake_up_blanket", "speed": 4.0},
        )
        run_id = started.json()["run_id"]
        steps = _dedupe_steps(await _wait_for_thread_status(client, run_id))
        actions = (await client.get("/api/actions")).json()

    final = steps[-1]["payload"]
    assert final["thread_status"] == "failed"
    assert "没有完成" in final["detail"]
    assert "device_online" in final["detail"]
    rgb_actions = [a for a in actions if a["capability"] == "set_rgb_indicator"]
    assert len(rgb_actions) == 1
    assert rgb_actions[0]["status"] == "failed"
    assert rgb_actions[0]["error_code"] == "SAFETY_CHECK_FAILED"


@pytest.mark.asyncio
async def test_temperature_cooling_scenario_still_works() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/debug/mock-activity",
            json={"step_delay_ms": 500},
        )
        run_id = started.json()["run_id"]
        steps = await _wait_for_thread_status(client, run_id)

    assert started.json()["scenario"] == "temperature_cooling"
    assert [event["payload"]["step_index"] for event in steps] == list(range(1, 8))
    assert steps[-1]["payload"]["thread_status"] == "completed"
