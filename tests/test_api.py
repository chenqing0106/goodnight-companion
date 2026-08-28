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
        response = await client.post("/api/debug/observations", json=payload)
        state = (await client.get("/api/state")).json()

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
    ]
    assert [tool["name"] for tool in tools] == [
        "move_phone_to_dock",
        "turn_off_light",
        "stop_all_motion",
        "set_rgb_indicator",
        "set_led_mode",
    ]
    assert response.status_code == 200
    assert [item["status"] for item in response.json()["actions"]] == [
        "succeeded",
        "succeeded",
    ]
    assert state["phone_location"] == "dock"
    assert state["light_on"] is False


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
