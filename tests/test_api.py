import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from goodnight_agent.api.app import create_app
from goodnight_agent.devices.memory import InMemoryDeviceGateway


@pytest.mark.asyncio
async def test_health_and_debug_observation() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0))
    payload = {
        "source": "api-test",
        "facts": {
            "person_in_bed": True,
            "person_motion": "still",
            "stable_for_seconds": 960,
            "phone_location": "operation_zone",
            "light_on": True,
            "sleep_window": True,
            "device_states": {"mock-arm": "online"},
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        root = await client.get("/")
        assert (await client.get("/health")).json() == {"status": "ok"}
        devices = (await client.get("/api/devices")).json()
        tools = (await client.get("/api/tools")).json()
        automation = (await client.get("/api/automation")).json()
        response = await client.post("/api/debug/observations", json=payload)
        state = (await client.get("/api/state")).json()
        recent = (await client.get("/api/events/recent", params={"limit": 2})).json()

    assert root.status_code == 307
    assert root.headers["location"] == "/docs"
    assert len(devices) == 1
    assert devices[0]["device_id"] == "mock-arm"
    assert devices[0]["availability"] == "online"
    assert devices[0]["capabilities_known"] is True
    assert devices[0]["capabilities"] == [
        "move_phone_to_dock",
        "turn_off_light",
        "stop_all_motion",
        "set_rgb_indicator",
        "set_led_mode",
    ]
    assert [tool["name"] for tool in tools] == [
        "move_phone_to_dock",
        "turn_off_light",
        "stop_all_motion",
        "set_rgb_indicator",
        "set_led_mode",
    ]
    assert response.status_code == 200
    assert automation == {
        "enabled": False,
        "rule": None,
        "required_samples": None,
    }
    assert len(recent) == 2
    assert all("event_id" in event for event in recent)
    assert [item["status"] for item in response.json()["actions"]] == [
        "succeeded",
        "succeeded",
    ]
    assert state["phone_location"] == "dock"
    assert state["light_on"] is False


@pytest.mark.asyncio
async def test_api_controls_rgb_and_led_modes() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        rgb = await client.post(
            "/api/devices/mock-arm/control",
            json={"capability": "set_rgb_indicator", "mode": 2},
        )
        led = await client.post(
            "/api/devices/mock-arm/control",
            json={"capability": "set_led_mode", "mode": 9},
        )
        invalid_rgb = await client.post(
            "/api/devices/mock-arm/control",
            json={"capability": "set_rgb_indicator", "mode": 4},
        )
        missing = await client.post(
            "/api/devices/missing/control",
            json={"capability": "set_led_mode", "mode": 1},
        )
        state = (await client.get("/api/state")).json()

    assert rgb.status_code == 200
    assert rgb.json()["actions"][0]["status"] == "succeeded"
    assert led.status_code == 200
    assert led.json()["actions"][0]["status"] == "succeeded"
    assert invalid_rgb.status_code == 422
    assert missing.status_code == 404
    assert state["rgb_indicator_mode"] == 2
    assert state["led_mode"] == 9


@pytest.mark.asyncio
async def test_api_can_stop_entire_run_idempotently() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0.1))
    payload = {
        "source": "api-run-stop-test",
        "facts": {
            "person_in_bed": True,
            "person_motion": "still",
            "stable_for_seconds": 960,
            "phone_location": "operation_zone",
            "light_on": True,
            "sleep_window": True,
            "device_states": {"mock-arm": "online"},
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        processing = asyncio.create_task(client.post("/api/debug/observations", json=payload))

        run_id = None
        for _ in range(100):
            actions = (await client.get("/api/actions")).json()
            running = [action for action in actions if action["status"] == "executing"]
            if running:
                run_id = running[0]["run_id"]
                break
            await asyncio.sleep(0.005)
        assert run_id is not None

        stopped = await client.post(f"/api/runs/{run_id}/stop")
        repeated_pending = await client.post(f"/api/runs/{run_id}/stop")
        workflow_response = await processing
        repeated = await client.post(f"/api/runs/{run_id}/stop")
        missing = await client.post("/api/runs/run_missing/stop")

    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stop_requested"
    assert repeated_pending.status_code == 200
    assert repeated_pending.json()["status"] == "stop_requested"
    assert [action["status"] for action in workflow_response.json()["actions"]] == [
        "stopped",
        "skipped",
    ]
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "stopped"
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_mock_activity_publishes_a_persistent_sequence() -> None:
    app = create_app(InMemoryDeviceGateway(step_delay=0))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/debug/mock-activity",
            json={"step_delay_ms": 500},
        )
        repeated = await client.post(
            "/api/debug/mock-activity",
            json={"step_delay_ms": 500},
        )
        await asyncio.sleep(3.2)
        recent = (await client.get("/api/events/recent", params={"limit": 100})).json()
        actions = (await client.get("/api/actions")).json()
        state = (await client.get("/api/state")).json()

    assert started.status_code == 200
    assert repeated.status_code == 409
    run_id = started.json()["run_id"]
    steps = [
        event
        for event in recent
        if event["event_type"] == "activity.step" and event["run_id"] == run_id
    ]
    assert [event["payload"]["step_index"] for event in steps] == list(range(1, 8))
    assert steps[-1]["payload"]["thread_status"] == "completed"
    assert steps[-1]["payload"]["hardware_control"] is True
    rgb_actions = [
        action for action in actions if action["capability"] == "set_rgb_indicator"
    ]
    assert len(rgb_actions) == 1
    assert rgb_actions[0]["parameters"] == {"mode": 3}
    assert rgb_actions[0]["status"] == "succeeded"
    assert state["rgb_indicator_mode"] == 3
