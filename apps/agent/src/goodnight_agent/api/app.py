from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from goodnight_agent.agent.mock_activity import (
    SIMULATED_TOOL_NAMES,
    MockActivityRequest,
    MockActivitySimulator,
    MockActivityStartResult,
    MockActivityStatus,
    MockActivityStopResult,
    simulated_device_record,
)
from goodnight_agent.agent.scene_evaluator import SceneEvaluator
from goodnight_agent.agent.sensor_automation import VitalsSignalAutomation
from goodnight_agent.agent.workflow import RunStopResult, SimpleWorkflow, WorkflowResult
from goodnight_agent.devices.base import DeviceGateway, SensorEventSource, SensorGateway
from goodnight_agent.devices.env_s3 import EnvS3MqttGateway
from goodnight_agent.devices.memory import InMemoryDeviceGateway
from goodnight_agent.devices.mqtt import MqttDeviceGateway
from goodnight_agent.devices.registry import (
    DeviceRegistry,
    InMemoryDeviceRegistry,
    OverlayDeviceRegistry,
)
from goodnight_agent.devices.robot_arm import ARM_CAPABILITIES, RobotArmHttpGateway
from goodnight_agent.devices.router import CapabilityGatewayRouter
from goodnight_agent.domain.models import (
    Action,
    ActionRequest,
    ActionStatus,
    Decision,
    DeviceAvailability,
    DeviceRecord,
    DomainEvent,
    Observation,
    SensorReading,
    new_id,
)
from goodnight_agent.infrastructure.events import InMemoryEventPublisher
from goodnight_agent.infrastructure.repositories import InMemoryActionRepository
from goodnight_agent.tools.executor import ToolExecutor
from goodnight_agent.tools.models import ToolDefinition
from goodnight_agent.tools.registry import ToolError, ToolRegistry, build_default_tool_registry


class DeviceControlRequest(BaseModel):
    capability: Literal["set_rgb_indicator", "set_led_mode"]
    mode: Annotated[int, Field(strict=True, ge=0, le=9)]


ArmCapability = Literal[
    "arm_take_phone",
    "arm_shake_toy",
    "arm_pull_blanket",
    "arm_insert_item",
    "arm_storytelling",
]


class ArmActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: ArmCapability


class ArmActionStartResult(BaseModel):
    run_id: str
    capability: str
    device_id: str
    status: Literal["accepted"] = "accepted"


TERMINAL_ACTION_STATUSES = {
    ActionStatus.SUCCEEDED,
    ActionStatus.FAILED,
    ActionStatus.STOPPED,
    ActionStatus.SKIPPED,
}


@dataclass
class AppServices:
    workflow: SimpleWorkflow
    events: InMemoryEventPublisher
    actions: InMemoryActionRepository
    gateway: DeviceGateway
    registry: DeviceRegistry
    tools: ToolRegistry
    mock_activity: MockActivitySimulator
    simulated_gateway: InMemoryDeviceGateway
    sensor_automation: VitalsSignalAutomation | None = None
    arm_gateway: RobotArmHttpGateway | None = None
    background_tasks: set[asyncio.Task[object]] = field(default_factory=set)


def _build_registry(
    actual_gateway: DeviceGateway,
    registry: DeviceRegistry | None,
    device_id: str,
) -> DeviceRegistry:
    sim_record = simulated_device_record()
    if registry is None:
        if isinstance(actual_gateway, (MqttDeviceGateway, EnvS3MqttGateway)):
            return OverlayDeviceRegistry(
                primary=actual_gateway,
                overlay=InMemoryDeviceRegistry({sim_record.device_id: sim_record}),
            )
        memory_registry = InMemoryDeviceRegistry.with_mock_device(device_id)
        memory_registry.devices[sim_record.device_id] = sim_record
        return memory_registry
    if isinstance(registry, InMemoryDeviceRegistry):
        registry.devices.setdefault(sim_record.device_id, sim_record)
        return registry
    return OverlayDeviceRegistry(
        primary=registry,
        overlay=InMemoryDeviceRegistry({sim_record.device_id: sim_record}),
    )


def _register_arm_device(registry: DeviceRegistry, record: DeviceRecord) -> None:
    """把机械臂设备登记进本地记录，让安全检查能看到它在线、能力齐备。"""
    if isinstance(registry, OverlayDeviceRegistry):
        registry.overlay.devices[record.device_id] = record
    elif isinstance(registry, InMemoryDeviceRegistry):
        registry.devices[record.device_id] = record


def build_arm_gateway_from_environment() -> RobotArmHttpGateway | None:
    """设置 GOODNIGHT_ARM_BASE_URL 后启用机械臂 HTTP 网关（ASUS 场景服务）。"""
    base_url = os.getenv("GOODNIGHT_ARM_BASE_URL")
    if not base_url:
        return None
    return RobotArmHttpGateway(
        base_url=base_url.rstrip("/"),
        poll_interval=float(os.getenv("GOODNIGHT_ARM_POLL_INTERVAL", "1.0")),
        request_timeout=float(os.getenv("GOODNIGHT_ARM_REQUEST_TIMEOUT", "5.0")),
        trigger_timeout=float(os.getenv("GOODNIGHT_ARM_TRIGGER_TIMEOUT", "30.0")),
    )


def build_services(
    gateway: DeviceGateway | None = None,
    registry: DeviceRegistry | None = None,
) -> AppServices:
    actual_gateway = gateway or build_gateway_from_environment()
    device_id = (
        actual_gateway.device_id
        if isinstance(actual_gateway, EnvS3MqttGateway)
        else os.getenv("GOODNIGHT_MQTT_DEVICE_ID", "mock-arm")
    )
    actual_registry = _build_registry(actual_gateway, registry, device_id)
    simulated_gateway = InMemoryDeviceGateway(
        step_delay=float(os.getenv("GOODNIGHT_SIM_STEP_DELAY", "0.25"))
    )
    arm_gateway = build_arm_gateway_from_environment()
    gateway_overrides: dict[str, DeviceGateway] = {
        name: simulated_gateway for name in SIMULATED_TOOL_NAMES
    }
    if arm_gateway is not None:
        gateway_overrides.update({name: arm_gateway for name in ARM_CAPABILITIES})
        _register_arm_device(
            actual_registry,
            DeviceRecord(
                device_id=arm_gateway.device_id,
                availability=DeviceAvailability.ONLINE,
                capabilities=list(ARM_CAPABILITIES),
                capabilities_known=True,
            ),
        )
    routed_gateway = CapabilityGatewayRouter(
        default=actual_gateway,
        overrides=gateway_overrides,
    )
    events = InMemoryEventPublisher()
    actions = InMemoryActionRepository()
    tool_registry = build_default_tool_registry()
    # 机械臂一次性轨迹回放通常超过 30 秒；启用机械臂且未显式配置时放宽到 120 秒
    default_timeout = "120000" if arm_gateway is not None else "30000"
    command_timeout_ms = int(os.getenv("GOODNIGHT_COMMAND_TIMEOUT_MS", default_timeout))
    workflow = SimpleWorkflow(
        gateway=routed_gateway,
        registry=actual_registry,
        tool_executor=ToolExecutor(registry=tool_registry, gateway=routed_gateway),
        publisher=events,
        actions=actions,
        evaluator=SceneEvaluator(device_id=device_id),
        command_timeout_ms=command_timeout_ms,
    )
    mock_activity = MockActivitySimulator(
        publisher=events,
        workflow=workflow,
        device_id=device_id,
    )
    sensor_automation = None
    if isinstance(actual_gateway, SensorEventSource) and _environment_flag(
        "GOODNIGHT_SENSOR_AUTOMATION_ENABLED"
    ):
        sensor_automation = VitalsSignalAutomation(
            source=actual_gateway,
            workflow=workflow,
            publisher=events,
            device_id=device_id,
            required_samples=int(os.getenv("GOODNIGHT_VITALS_REQUIRED_SAMPLES", "3")),
            freshness_seconds=float(os.getenv("GOODNIGHT_SENSOR_FRESHNESS_SECONDS", "5")),
            cooldown_seconds=float(os.getenv("GOODNIGHT_AUTOMATION_COOLDOWN_SECONDS", "10")),
        )
    return AppServices(
        workflow=workflow,
        events=events,
        actions=actions,
        gateway=actual_gateway,
        registry=actual_registry,
        tools=tool_registry,
        mock_activity=mock_activity,
        simulated_gateway=simulated_gateway,
        sensor_automation=sensor_automation,
        arm_gateway=arm_gateway,
    )


def _environment_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
    if transport in {"env_s3_mqtt", "env-s3-mqtt"}:
        return EnvS3MqttGateway(
            host=os.getenv("GOODNIGHT_MQTT_HOST", "218.11.5.249"),
            port=int(os.getenv("GOODNIGHT_MQTT_PORT", "10317")),
            device_id=os.getenv("GOODNIGHT_MQTT_DEVICE_ID", "env-s3-01"),
            username=os.getenv("GOODNIGHT_MQTT_USERNAME"),
            password=os.getenv("GOODNIGHT_MQTT_PASSWORD"),
            mock_sensors=_environment_flag("GOODNIGHT_ENV_S3_MOCK_SENSORS"),
        )
    raise ValueError(f"unsupported GOODNIGHT_DEVICE_TRANSPORT: {transport}")


def create_app(
    gateway: DeviceGateway | None = None,
    registry: DeviceRegistry | None = None,
) -> FastAPI:
    services = build_services(gateway, registry)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.services = services
        automation_task: asyncio.Task[None] | None = None
        if services.sensor_automation is not None:
            automation_task = asyncio.create_task(services.sensor_automation.run())
        try:
            yield
        finally:
            if automation_task is not None:
                automation_task.cancel()
                with suppress(asyncio.CancelledError):
                    await automation_task
            await services.mock_activity.close()
            await services.simulated_gateway.close()
            if services.arm_gateway is not None:
                await services.arm_gateway.close()
            await services.gateway.close()
            if services.registry is not services.gateway:
                await services.registry.close()

    application = FastAPI(
        title="Goodnight Agent",
        version="0.1.0",
        description="好梦鸟 Agent M1/M2 的可运行验证服务",
        lifespan=lifespan,
    )
    application.state.services = services

    @application.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/debug/observations", response_model=WorkflowResult)
    async def submit_observation(observation: Observation) -> WorkflowResult:
        return await services.workflow.process_observation(observation)

    @application.post(
        "/api/debug/mock-activity",
        response_model=MockActivityStartResult,
    )
    async def start_mock_activity(
        request: MockActivityRequest,
    ) -> MockActivityStartResult:
        try:
            return await services.mock_activity.start(request)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get(
        "/api/debug/mock-activity",
        response_model=MockActivityStatus,
    )
    async def mock_activity_status() -> MockActivityStatus:
        return services.mock_activity.status()

    @application.post(
        "/api/debug/mock-activity/stop",
        response_model=MockActivityStopResult,
    )
    async def stop_mock_activity() -> MockActivityStopResult:
        return await services.mock_activity.stop()

    @application.get("/api/state")
    async def get_state() -> dict[str, object]:
        return services.workflow.world_state.model_dump(mode="json")

    @application.get("/api/devices", response_model=list[DeviceRecord])
    async def list_devices() -> list[DeviceRecord]:
        return await services.registry.list_devices()

    @application.get(
        "/api/devices/{device_id}/sensors",
        response_model=list[SensorReading],
    )
    async def list_sensor_readings(device_id: str) -> list[SensorReading]:
        if not isinstance(services.gateway, SensorGateway):
            raise HTTPException(status_code=404, detail="device has no sensor data source")
        if await services.registry.get_device(device_id) is None:
            raise HTTPException(status_code=404, detail="device not found")
        return await services.gateway.list_sensor_readings(device_id)

    @application.post(
        "/api/devices/{device_id}/control",
        response_model=WorkflowResult,
    )
    async def control_device(
        device_id: str,
        request: DeviceControlRequest,
    ) -> WorkflowResult:
        if await services.registry.get_device(device_id) is None:
            raise HTTPException(status_code=404, detail="device not found")
        try:
            parameters = services.tools.validate_arguments(
                request.capability,
                {"mode": request.mode},
            )
        except ToolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        observation = Observation(source="admin_control", facts={}, confidence=1)
        decision = Decision(
            scene="manual_device_control",
            should_intervene=True,
            reason="后台手动控制灯光",
            confidence=1,
            proposed_actions=[
                ActionRequest(
                    capability=request.capability,
                    parameters=parameters,
                    device_id=device_id,
                )
            ],
        )
        return await services.workflow.process_observation(
            observation,
            proposed_decision=decision,
        )

    @application.get("/api/tools", response_model=list[ToolDefinition])
    async def list_tools() -> list[ToolDefinition]:
        return services.tools.list_definitions()

    @application.post(
        "/api/arm/actions",
        response_model=ArmActionStartResult,
        status_code=202,
    )
    async def start_arm_action(request: ArmActionRequest) -> ArmActionStartResult:
        """后台触发机械臂场景动作，立即返回 run_id。

        动作经 workflow 在后台执行，用 /api/actions 或 /api/events 跟踪进度；
        停止用 /api/runs/{run_id}/stop 或 /api/actions/{action_id}/stop。
        """
        arm = services.arm_gateway
        if arm is None:
            raise HTTPException(
                status_code=503,
                detail="机械臂网关未启用，请设置 GOODNIGHT_ARM_BASE_URL",
            )
        for action in await services.actions.list():
            if action.device_id == arm.device_id and action.status not in TERMINAL_ACTION_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=f"机械臂正在执行 {action.capability}（{action.action_id}）",
                )

        run_id = new_id("run")
        observation = Observation(source="admin_arm_control", facts={}, confidence=1)
        decision = Decision(
            scene="manual_arm_control",
            should_intervene=True,
            reason="后台手动触发机械臂动作",
            confidence=1,
            proposed_actions=[
                ActionRequest(
                    capability=request.capability,
                    parameters={},
                    device_id=arm.device_id,
                )
            ],
        )
        task = asyncio.create_task(
            services.workflow.process_observation(
                observation,
                run_id=run_id,
                proposed_decision=decision,
            )
        )
        services.background_tasks.add(task)

        def _discard(completed: asyncio.Task[object]) -> None:
            services.background_tasks.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(_discard)
        return ArmActionStartResult(
            run_id=run_id,
            capability=request.capability,
            device_id=arm.device_id,
        )

    @application.get("/api/automation")
    async def get_automation_status() -> dict[str, object]:
        automation = services.sensor_automation
        return {
            "enabled": automation is not None,
            "rule": "vitals_signal_indicator" if automation is not None else None,
            "required_samples": automation.required_samples if automation is not None else None,
        }

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

    @application.post("/api/runs/{run_id}/stop", response_model=RunStopResult)
    async def stop_run(run_id: str) -> RunStopResult:
        try:
            return await services.workflow.stop_run(run_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/events")
    async def stream_events(request: Request) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            yield ": connected\n\n"
            async for event in services.events.subscribe():
                if await request.is_disconnected():
                    return
                body = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                yield f"id: {event.event_id}\nevent: {event.event_type}\ndata: {body}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.get("/api/events/recent", response_model=list[DomainEvent])
    async def recent_events(
        limit: int = Query(default=100, ge=1, le=500),
        run_id: str | None = None,
    ) -> list[DomainEvent]:
        return services.events.recent(limit=limit, run_id=run_id)

    return application


app = create_app()
