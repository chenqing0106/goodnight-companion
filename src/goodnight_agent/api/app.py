from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from goodnight_agent.agent.scene_evaluator import SceneEvaluator
from goodnight_agent.agent.workflow import SimpleWorkflow, WorkflowResult
from goodnight_agent.devices.base import DeviceGateway
from goodnight_agent.devices.memory import InMemoryDeviceGateway
from goodnight_agent.devices.mqtt import MqttDeviceGateway
from goodnight_agent.domain.models import Action, Observation
from goodnight_agent.infrastructure.events import InMemoryEventPublisher
from goodnight_agent.infrastructure.repositories import InMemoryActionRepository


@dataclass
class AppServices:
    workflow: SimpleWorkflow
    events: InMemoryEventPublisher
    actions: InMemoryActionRepository
    gateway: DeviceGateway


def build_services(gateway: DeviceGateway | None = None) -> AppServices:
    actual_gateway = gateway or build_gateway_from_environment()
    events = InMemoryEventPublisher()
    actions = InMemoryActionRepository()
    workflow = SimpleWorkflow(
        gateway=actual_gateway,
        publisher=events,
        actions=actions,
        evaluator=SceneEvaluator(device_id=os.getenv("GOODNIGHT_MQTT_DEVICE_ID", "mock-arm")),
    )
    return AppServices(
        workflow=workflow,
        events=events,
        actions=actions,
        gateway=actual_gateway,
    )


def build_gateway_from_environment() -> DeviceGateway:
    transport = os.getenv("GOODNIGHT_DEVICE_TRANSPORT", "memory").lower()
    if transport == "memory":
        return InMemoryDeviceGateway(step_delay=0.25)
    if transport == "mqtt":
        return MqttDeviceGateway(
            host=os.getenv("GOODNIGHT_MQTT_HOST", "127.0.0.1"),
            port=int(os.getenv("GOODNIGHT_MQTT_PORT", "1883")),
            base_topic=os.getenv("GOODNIGHT_MQTT_BASE_TOPIC", "goodnight"),
            username=os.getenv("GOODNIGHT_MQTT_USERNAME"),
            password=os.getenv("GOODNIGHT_MQTT_PASSWORD"),
        )
    raise ValueError(f"unsupported GOODNIGHT_DEVICE_TRANSPORT: {transport}")


def create_app(gateway: DeviceGateway | None = None) -> FastAPI:
    services = build_services(gateway)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.services = services
        try:
            yield
        finally:
            await services.gateway.close()

    application = FastAPI(
        title="Goodnight Agent",
        version="0.1.0",
        description="好梦鸟 Agent M1/M2 的可运行验证服务",
        lifespan=lifespan,
    )
    application.state.services = services

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/debug/observations", response_model=WorkflowResult)
    async def submit_observation(observation: Observation) -> WorkflowResult:
        return await services.workflow.process_observation(observation)

    @application.get("/api/state")
    async def get_state() -> dict[str, object]:
        return services.workflow.world_state.model_dump(mode="json")

    @application.get("/api/actions", response_model=list[Action])
    async def list_actions() -> list[Action]:
        return await services.actions.list()

    @application.get("/api/actions/{action_id}", response_model=Action)
    async def get_action(action_id: str) -> Action:
        action = await services.actions.get(action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="action not found")
        return action

    @application.post("/api/actions/{action_id}/confirm", response_model=Action)
    async def confirm_action(action_id: str) -> Action:
        try:
            return await services.workflow.confirm(action_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/api/actions/{action_id}/stop", response_model=Action)
    async def stop_action(action_id: str) -> Action:
        try:
            return await services.workflow.stop(action_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/events")
    async def stream_events(request: Request) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            yield ": connected\n\n"
            async for event in services.events.subscribe():
                if await request.is_disconnected():
                    return
                body = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                yield f"event: {event.event_type}\ndata: {body}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return application


app = create_app()
