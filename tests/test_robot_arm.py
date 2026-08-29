"""RobotArmHttpGateway 单元测试。

用 httpx.MockTransport 模拟 ASUS 上的机械臂场景服务，
不需要真实硬件。运行方式见 INTEGRATION.md。
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from goodnight_agent.devices.robot_arm import RobotArmHttpGateway
from goodnight_agent.domain.models import DeviceCommand, DeviceCommandStatus


def make_gateway(
    handler,
    **overrides,
) -> RobotArmHttpGateway:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://arm.test",
    )
    return RobotArmHttpGateway(
        client=client,
        poll_interval=overrides.pop("poll_interval", 0.01),
        **overrides,
    )


def make_command(capability: str, timeout_ms: int = 5000) -> DeviceCommand:
    return DeviceCommand(
        action_id="act-test",
        device_id="panthera-arm",
        capability=capability,
        timeout_ms=timeout_ms,
    )


async def collect(gateway: RobotArmHttpGateway, command: DeviceCommand):
    return [status async for status in gateway.execute(command)]


async def test_one_shot_success() -> None:
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.url.path == "/api/scenes/take_phone02/replay" and request.method == "POST":
            return httpx.Response(202, json={"state": "running", "scene": "take_phone02"})
        if request.url.path == "/api/status":
            polls += 1
            if polls < 2:
                return httpx.Response(200, json={"running": True, "state": "running"})
            return httpx.Response(200, json={"running": False, "state": "completed"})
        return httpx.Response(404)

    gateway = make_gateway(handler)
    statuses = await collect(gateway, make_command("arm_take_phone"))

    assert [s.status for s in statuses] == [
        DeviceCommandStatus.ACCEPTED,
        DeviceCommandStatus.EXECUTING,
        DeviceCommandStatus.SUCCEEDED,
    ]
    assert statuses[-1].result["facts"]["arm_scene"] == "take_phone02"
    await gateway.close()


@pytest.mark.parametrize(
    ("capability", "path"),
    [
        ("arm_take_phone", "/api/scenes/take_phone02/replay"),
        ("arm_shake_toy", "/api/scenes/shake_toy02/replay"),
        ("arm_pull_blanket", "/api/application/blanket01/run"),
        ("arm_insert_item", "/api/application/insert02/run"),
    ],
)
async def test_one_shot_scene_mapping(capability: str, path: str) -> None:
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            called.append(request.url.path)
            return httpx.Response(202, json={"state": "running"})
        return httpx.Response(200, json={"running": False, "state": "completed"})

    gateway = make_gateway(handler)
    statuses = await collect(gateway, make_command(capability))

    assert called == [path]
    assert statuses[-1].status == DeviceCommandStatus.SUCCEEDED
    await gateway.close()


async def test_one_shot_busy_409() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "busy"})

    gateway = make_gateway(handler)
    statuses = await collect(gateway, make_command("arm_take_phone"))

    assert statuses[-1].status == DeviceCommandStatus.FAILED
    assert statuses[-1].error_code == "ARM_BUSY"
    await gateway.close()


async def test_one_shot_not_deployed_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(404, json={"detail": "scene not found"})
        return httpx.Response(200, json={"running": False})

    gateway = make_gateway(handler)
    statuses = await collect(gateway, make_command("arm_take_phone"))

    assert statuses[-1].status == DeviceCommandStatus.FAILED
    assert statuses[-1].error_code == "SCENE_NOT_DEPLOYED"
    await gateway.close()


async def test_one_shot_scene_failed_on_arm() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"state": "running"})
        return httpx.Response(200, json={"running": False, "state": "failed"})

    gateway = make_gateway(handler)
    statuses = await collect(gateway, make_command("arm_take_phone"))

    assert statuses[-1].status == DeviceCommandStatus.FAILED
    assert statuses[-1].error_code == "ARM_SCENE_FAILED"
    await gateway.close()


async def test_one_shot_manual_stop_calls_arm_stop() -> None:
    posted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(request.url.path)
            return httpx.Response(202, json={"state": "running"})
        return httpx.Response(200, json={"running": True, "state": "running"})

    gateway = make_gateway(handler)
    command = make_command("arm_take_phone")

    async def run():
        return [s async for s in gateway.execute(command)]

    task = asyncio.create_task(run())
    await asyncio.sleep(0.05)
    await gateway.stop(command.command_id)
    statuses = await task

    assert statuses[-1].status == DeviceCommandStatus.STOPPED
    assert "/api/arm/stop" in posted
    await gateway.close()


async def test_storytelling_manual_stop() -> None:
    posted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(request.url.path)
            return httpx.Response(202, json={"state": "running"})
        return httpx.Response(200, json={"running": True, "state": "running"})

    gateway = make_gateway(handler)
    command = make_command("arm_storytelling")

    async def run():
        return [s async for s in gateway.execute(command)]

    task = asyncio.create_task(run())
    await asyncio.sleep(0.05)
    await gateway.stop(command.command_id)
    statuses = await task

    assert statuses[-1].status == DeviceCommandStatus.STOPPED
    assert posted[0] == "/api/application/plant2/start"
    assert "/api/application/plant2/stop" in posted
    await gateway.close()


async def test_storytelling_stops_when_generator_closed() -> None:
    """workflow 超时/取消导致生成器关闭时，也要通知 ASUS 停止持续场景。"""
    posted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(request.url.path)
            return httpx.Response(202, json={"state": "running"})
        return httpx.Response(200, json={"running": True, "state": "running"})

    gateway = make_gateway(handler)
    command = make_command("arm_storytelling")
    stream = gateway.execute(command)
    first = await stream.__anext__()
    assert first.status == DeviceCommandStatus.ACCEPTED
    second = await stream.__anext__()
    assert second.status == DeviceCommandStatus.EXECUTING
    await stream.aclose()

    assert "/api/application/plant2/stop" in posted
    await gateway.close()


async def test_unknown_capability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    gateway = make_gateway(handler)
    statuses = await collect(gateway, make_command("arm_nonexistent"))

    assert statuses[-1].status == DeviceCommandStatus.FAILED
    assert statuses[-1].error_code == "UNSUPPORTED_CAPABILITY"
    await gateway.close()


# ---- /api/arm/actions 端点集成测试 ----


def arm_ok_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "POST":
        return httpx.Response(202, json={"state": "running"})
    return httpx.Response(200, json={"running": False, "state": "completed"})


def build_arm_app(monkeypatch, handler):
    from goodnight_agent.api.app import create_app
    from goodnight_agent.devices.memory import InMemoryDeviceGateway

    monkeypatch.setenv("GOODNIGHT_ARM_BASE_URL", "http://arm.test")
    monkeypatch.setenv("GOODNIGHT_COMMAND_TIMEOUT_MS", "5000")
    app = create_app(InMemoryDeviceGateway(step_delay=0))
    arm = app.state.services.arm_gateway
    assert arm is not None
    arm.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://arm.test",
    )
    arm.poll_interval = 0.01
    return app


async def wait_terminal(client, run_id: str) -> dict:
    deadline = asyncio.get_running_loop().time() + 5
    while asyncio.get_running_loop().time() < deadline:
        actions = (await client.get("/api/actions")).json()
        match = [a for a in actions if a["run_id"] == run_id]
        if match and match[0]["status"] in {
            "succeeded",
            "failed",
            "stopped",
            "skipped",
        }:
            return match[0]
        await asyncio.sleep(0.02)
    raise AssertionError("机械臂动作未在预期时间内结束")


async def test_arm_action_endpoint_runs_to_success(monkeypatch) -> None:
    app = build_arm_app(monkeypatch, arm_ok_handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/arm/actions",
            json={"capability": "arm_take_phone"},
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        action = await wait_terminal(client, run_id)

    assert action["capability"] == "arm_take_phone"
    assert action["device_id"] == "panthera-arm"
    assert action["status"] == "succeeded"


async def test_arm_action_endpoint_rejects_when_busy(monkeypatch) -> None:
    def slow_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"state": "running"})
        return httpx.Response(200, json={"running": True, "state": "running"})

    app = build_arm_app(monkeypatch, slow_handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/arm/actions",
            json={"capability": "arm_storytelling"},
        )
        assert first.status_code == 202
        await asyncio.sleep(0.1)
        second = await client.post(
            "/api/arm/actions",
            json={"capability": "arm_take_phone"},
        )
        assert second.status_code == 409
        stop = await client.post(f"/api/runs/{first.json()['run_id']}/stop")
        assert stop.status_code == 200
        action = await wait_terminal(client, first.json()["run_id"])

    assert action["status"] == "stopped"


async def test_arm_action_endpoint_disabled_without_env() -> None:
    from goodnight_agent.api.app import create_app
    from goodnight_agent.devices.memory import InMemoryDeviceGateway

    app = create_app(InMemoryDeviceGateway(step_delay=0))
    assert app.state.services.arm_gateway is None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/arm/actions",
            json={"capability": "arm_take_phone"},
        )
    assert response.status_code == 503
