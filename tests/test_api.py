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
        response = await client.post("/api/debug/observations", json=payload)
        state = (await client.get("/api/state")).json()

    assert root.status_code == 307
    assert root.headers["location"] == "/docs"
    assert response.status_code == 200
    assert [item["status"] for item in response.json()["actions"]] == [
        "succeeded",
        "succeeded",
    ]
    assert state["phone_location"] == "dock"
    assert state["light_on"] is False
