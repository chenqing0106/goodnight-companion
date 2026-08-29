from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from goodnight_agent.agent.workflow import SimpleWorkflow
from goodnight_agent.domain.models import (
    Action,
    ActionRequest,
    ActionStatus,
    Decision,
    DeviceAvailability,
    DeviceRecord,
    DomainEvent,
    Observation,
    new_id,
)
from goodnight_agent.infrastructure.events import EventPublisher

SIMULATED_DEVICE_ID = "sim-arm"
SIMULATED_TOOL_NAMES = ("turn_on_light", "pull_blanket", "reset_arm")
REAL_TOOL_NAMES = ("set_rgb_indicator", "set_led_mode")

WAKE_UP_SUBJECT = "渐进唤醒"
TEMPERATURE_SUBJECT = "睡前温度调节"


def simulated_device_record() -> DeviceRecord:
    return DeviceRecord(
        device_id=SIMULATED_DEVICE_ID,
        availability=DeviceAvailability.ONLINE,
        capabilities=list(SIMULATED_TOOL_NAMES),
        capabilities_known=True,
    )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class MockActivityRequest(BaseModel):
    scenario: Literal["temperature_cooling", "wake_up_blanket"] = "temperature_cooling"
    step_delay_ms: int = Field(default=2_200, ge=500, le=5_000)
    speed: float = Field(default=1.0, ge=0.5, le=4.0)


class MockActivityStartResult(BaseModel):
    run_id: str
    monitor_id: str
    scenario: str = "temperature_cooling"
    status: Literal["running"] = "running"
    total_steps: int
    step_delay_ms: int


class MockActivityStopResult(BaseModel):
    run_id: str | None = None
    status: Literal["stopped", "not_running"]


class MockActivityStatus(BaseModel):
    running: bool
    run_id: str | None = None
    scenario: str | None = None


@dataclass(frozen=True, slots=True)
class _ActivityStep:
    phase: str
    title: str
    detail: str
    evidence: list[str] = field(default_factory=list)


_TEMPERATURE_COOLING_STEPS = [
    _ActivityStep(
        phase="observation",
        title="我注意到房间温度偏高",
        detail="当前 27.2°C，舒适区上限为 26°C。先继续观察，不立即调整。",
        evidence=["温度 27.2°C", "第 1 次偏高"],
    ),
    _ActivityStep(
        phase="evaluation",
        title="温度仍然偏高",
        detail="已经连续偏高 2/3 次。如果下一次仍然偏高，我会模拟降低温度。",
        evidence=["连续偏高 2/3", "数据仍然新鲜"],
    ),
    _ActivityStep(
        phase="conclusion",
        title="判断成立",
        detail="连续 3 次温度偏高，可以排除一次瞬时波动。",
        evidence=["连续偏高 3/3", "判断置信度高"],
    ),
    _ActivityStep(
        phase="plan",
        title="我准备模拟降低温度",
        detail="计划将三色 LED 调整为蓝色，让温度变化方向保持可见。",
        evidence=["目标：模拟降温", "预期状态：蓝色"],
    ),
    _ActivityStep(
        phase="safety",
        title="正在确认能否执行",
        detail="设备在线、能力可用，并且当前没有冲突动作。",
        evidence=["ENV-S3 在线", "支持三色 LED", "无冲突动作"],
    ),
    _ActivityStep(
        phase="action",
        title="正在调整温度指示灯",
        detail="控制指令已经发送，正在等待 ENV-S3 返回实际状态。",
        evidence=["目标：蓝色", "等待硬件确认"],
    ),
    _ActivityStep(
        phase="verification",
        title="已经完成",
        detail="硬件确认三色 LED 为蓝色，本次模拟降温完成。",
        evidence=["硬件回执：blue", "结果与计划一致"],
    ),
]


@dataclass(frozen=True, slots=True)
class WakeUpToolCall:
    capability: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def execution(self) -> Literal["real", "simulated"]:
        return "real" if self.capability in REAL_TOOL_NAMES else "simulated"


@dataclass(frozen=True, slots=True)
class WakeUpStep:
    kind: Literal["narrative", "checks", "plan", "tool"]
    clock: str
    wait_s: float
    phase: str
    text: str
    checks: tuple[str, ...] = ()
    plan: tuple[str, ...] = ()
    tools: tuple[WakeUpToolCall, ...] = ()


def build_wake_up_steps(*, led_alert_mode: int, led_calm_mode: int) -> list[WakeUpStep]:
    """F5 渐进唤醒的固定场景定义：文案、检查项、计划和执行顺序保持稳定。"""

    return [
        WakeUpStep(
            kind="narrative",
            clock="07:30:01",
            wait_s=0,
            phase="observation",
            text="检测到闹钟已经响起，用户仍保持躺卧状态，当前环境偏冷。",
        ),
        WakeUpStep(
            kind="narrative",
            clock="07:30:02",
            wait_s=1.0,
            phase="evaluation",
            text=(
                "渐进唤醒条件已经满足。我将先改善起床环境并进行温和提醒，"
                "在用户持续无响应时逐步提高唤醒强度。"
            ),
        ),
        WakeUpStep(
            kind="checks",
            clock="07:30:02",
            wait_s=0.8,
            phase="safety",
            text="安全检查已通过，可以按计划执行。",
            checks=(
                "灯光设备在线",
                "机械臂安全区域有效",
                "被角位于预设操作位置",
                "用户未提出停止",
            ),
        ),
        WakeUpStep(
            kind="plan",
            clock="07:30:02",
            wait_s=0.8,
            phase="plan",
            text="行动计划已经生成。",
            plan=(
                "调节环境温度并进行第一次提醒",
                "等待并重新判断用户状态",
                "无响应时逐步增强灯光和情绪表达",
                "持续无响应时缓慢拉动被角，检测到起床后立即停止",
            ),
        ),
        WakeUpStep(
            kind="tool",
            clock="07:30:03",
            wait_s=1.0,
            phase="action",
            text="已启动制热状态，RGB 指示灯切换为红色。",
            tools=(WakeUpToolCall("set_rgb_indicator", {"mode": 1}),),
        ),
        WakeUpStep(
            kind="narrative",
            clock="07:30:05",
            wait_s=1.5,
            phase="action",
            text="已进行第一次起床提醒，等待用户回应。",
        ),
        WakeUpStep(
            kind="tool",
            clock="07:31:05",
            wait_s=2.0,
            phase="action",
            text="用户仍未起床，卧室灯光正在逐渐打开。",
            tools=(WakeUpToolCall("turn_on_light"),),
        ),
        WakeUpStep(
            kind="tool",
            clock="07:31:35",
            wait_s=2.0,
            phase="action",
            text="用户持续无响应，灯带切换为低亮红光，机械臂开始缓慢拉动预设被角。",
            tools=(
                WakeUpToolCall("set_led_mode", {"mode": led_alert_mode}),
                WakeUpToolCall("pull_blanket", {"speed_profile": "gentle"}),
            ),
        ),
        WakeUpStep(
            kind="tool",
            clock="07:31:38",
            wait_s=1.5,
            phase="action",
            text="检测到用户已经坐起，拉被动作已停止，机械臂正在复位。",
            tools=(WakeUpToolCall("reset_arm"),),
        ),
        WakeUpStep(
            kind="tool",
            clock="07:31:40",
            wait_s=1.5,
            phase="verification",
            text=(
                "灯带切换为柔和绿光，RGB 指示灯切换为绿色。"
                "当前温度适宜，渐进唤醒任务已经完成。"
            ),
            tools=(
                WakeUpToolCall("set_led_mode", {"mode": led_calm_mode}),
                WakeUpToolCall("set_rgb_indicator", {"mode": 2}),
            ),
        ),
    ]


@dataclass
class MockActivitySimulator:
    publisher: EventPublisher
    workflow: SimpleWorkflow
    device_id: str
    led_alert_mode: int = field(
        default_factory=lambda: _env_int("GOODNIGHT_LED_MODE_ALERT", 7)
    )
    led_calm_mode: int = field(
        default_factory=lambda: _env_int("GOODNIGHT_LED_MODE_CALM", 8)
    )
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _run_id: str | None = field(default=None, init=False)
    _scenario: str | None = field(default=None, init=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def start(self, request: MockActivityRequest) -> MockActivityStartResult:
        if self._task is not None and not self._task.done():
            raise RuntimeError("a mock activity is already running")

        run_id = new_id("run")
        self._run_id = run_id
        self._scenario = request.scenario
        self._stop_event = asyncio.Event()

        if request.scenario == "wake_up_blanket":
            monitor_id = f"wakeup:{new_id('monitor')}"
            steps = build_wake_up_steps(
                led_alert_mode=self.led_alert_mode,
                led_calm_mode=self.led_calm_mode,
            )
            self._task = asyncio.create_task(
                self._run_wake_up(
                    run_id=run_id,
                    monitor_id=monitor_id,
                    steps=steps,
                    speed=request.speed,
                )
            )
            return MockActivityStartResult(
                run_id=run_id,
                monitor_id=monitor_id,
                scenario=request.scenario,
                total_steps=len(steps),
                step_delay_ms=request.step_delay_ms,
            )

        monitor_id = f"temperature:{new_id('monitor')}"
        steps = _TEMPERATURE_COOLING_STEPS
        await self._publish_step(run_id, monitor_id, steps, 0)
        self._task = asyncio.create_task(
            self._continue(
                run_id=run_id,
                monitor_id=monitor_id,
                steps=steps,
                step_delay_ms=request.step_delay_ms,
            )
        )
        return MockActivityStartResult(
            run_id=run_id,
            monitor_id=monitor_id,
            scenario=request.scenario,
            total_steps=len(steps),
            step_delay_ms=request.step_delay_ms,
        )

    def status(self) -> MockActivityStatus:
        running = self._task is not None and not self._task.done()
        return MockActivityStatus(
            running=running,
            run_id=self._run_id if running else None,
            scenario=self._scenario if running else None,
        )

    async def stop(self) -> MockActivityStopResult:
        run_id = self._run_id
        if run_id is None or self._task is None or self._task.done():
            return MockActivityStopResult(run_id=None, status="not_running")

        self._stop_event.set()
        with suppress(LookupError):
            await self.workflow.stop_run(run_id)
        with suppress(TimeoutError):
            async with asyncio.timeout(5):
                await self._task
        return MockActivityStopResult(run_id=run_id, status="stopped")

    async def _wait(self, seconds: float) -> bool:
        """Sleep for ``seconds``; return True immediately when stopped."""
        if self._stop_event.is_set():
            return True
        if seconds <= 0:
            return False
        with suppress(TimeoutError):
            async with asyncio.timeout(seconds):
                await self._stop_event.wait()
        return self._stop_event.is_set()

    # ------------------------------------------------------------------
    # F5 渐进唤醒场景

    async def _run_wake_up(
        self,
        *,
        run_id: str,
        monitor_id: str,
        steps: list[WakeUpStep],
        speed: float,
    ) -> None:
        try:
            for index, step in enumerate(steps):
                if await self._wait(step.wait_s / speed):
                    await self._handle_wake_up_stopped(run_id, monitor_id, steps)
                    return
                if step.kind != "tool":
                    await self._publish_wake_up_step(
                        run_id, monitor_id, steps, index, thread_status="running"
                    )
                    continue
                outcome = await self._execute_wake_up_tool_step(
                    run_id, monitor_id, steps, index
                )
                if outcome == "failed":
                    return
                if outcome == "stopped":
                    await self._handle_wake_up_stopped(run_id, monitor_id, steps)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapters may raise vendor errors
            await self._publish_wake_up_failure(
                run_id,
                monitor_id,
                steps,
                len(steps) - 1,
                detail=f"场景执行出现异常：{exc}",
            )
        finally:
            if self._run_id == run_id:
                self._run_id = None

    async def _execute_wake_up_tool_step(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[WakeUpStep],
        index: int,
    ) -> Literal["ok", "failed", "stopped"]:
        step = steps[index]
        await self._publish_wake_up_step(
            run_id, monitor_id, steps, index, thread_status="running", tool_status="running"
        )

        receipts: list[dict[str, Any]] = []
        for call in step.tools:
            if self._stop_event.is_set():
                return "stopped"
            action = await self._execute_tool(run_id, call)
            receipts.append(self._tool_receipt(call, action))
            if action is None or action.status is not ActionStatus.SUCCEEDED:
                if self._stop_event.is_set() or (
                    action is not None and action.status is ActionStatus.STOPPED
                ):
                    return "stopped"
                reason = (
                    action.reason
                    if action is not None and action.reason
                    else "设备没有确认这次操作"
                )
                await self._publish_wake_up_step(
                    run_id,
                    monitor_id,
                    steps,
                    index,
                    thread_status="failed",
                    tool_status="failed",
                    receipts=receipts,
                    detail=f"没有完成：{reason}",
                )
                return "failed"

        final = index == len(steps) - 1
        await self._publish_wake_up_step(
            run_id,
            monitor_id,
            steps,
            index,
            thread_status="completed" if final else "running",
            tool_status="done",
            receipts=receipts,
        )
        return "ok"

    async def _handle_wake_up_stopped(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[WakeUpStep],
    ) -> None:
        stop_index = len(steps)
        reset_call = WakeUpToolCall("reset_arm")
        await self._publish_wake_up_stop_step(
            run_id,
            monitor_id,
            steps,
            stop_index,
            detail="场景已停止，后续步骤不再执行。机械臂正在复位。",
            receipts=[self._pending_receipt(reset_call)],
        )
        # 复位使用新的 workflow run，避免被已停止的 run 跳过。
        action = await self._execute_tool(new_id("run"), reset_call)
        detail = (
            "场景已停止，机械臂已复位。"
            if action is not None and action.status is ActionStatus.SUCCEEDED
            else "场景已停止，机械臂复位没有完成，请检查设备状态。"
        )
        await self._publish_wake_up_stop_step(
            run_id,
            monitor_id,
            steps,
            stop_index,
            detail=detail,
            receipts=[self._tool_receipt(reset_call, action)],
        )

    async def _execute_tool(self, run_id: str, call: WakeUpToolCall) -> Action | None:
        device_id = self.device_id if call.execution == "real" else SIMULATED_DEVICE_ID
        decision = Decision(
            scene="wake_up_blanket",
            should_intervene=True,
            reason="F5 渐进唤醒场景执行预设动作",
            confidence=1,
            confirmation="automatic",
            proposed_actions=[
                ActionRequest(
                    capability=call.capability,
                    device_id=device_id,
                    parameters=dict(call.parameters),
                )
            ],
        )
        result = await self.workflow.process_observation(
            Observation(
                source="wake_up_blanket",
                facts={"simulated_scenario": "wake_up_blanket"},
                confidence=1,
            ),
            run_id=run_id,
            proposed_decision=decision,
        )
        return result.actions[0] if result.actions else None

    def _tool_device_id(self, call: WakeUpToolCall) -> str:
        return self.device_id if call.execution == "real" else SIMULATED_DEVICE_ID

    def _pending_receipt(self, call: WakeUpToolCall) -> dict[str, Any]:
        return {
            "name": call.capability,
            "parameters": dict(call.parameters),
            "execution": call.execution,
            "device_id": self._tool_device_id(call),
            "status": "running",
            "receipt": None,
        }

    def _tool_receipt(self, call: WakeUpToolCall, action: Action | None) -> dict[str, Any]:
        return {
            "name": call.capability,
            "parameters": dict(call.parameters),
            "execution": call.execution,
            "device_id": self._tool_device_id(call),
            "status": action.status if action is not None else "missing",
            "receipt": action.reason if action is not None else None,
        }

    async def _publish_wake_up_step(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[WakeUpStep],
        index: int,
        *,
        thread_status: Literal["running", "completed", "failed"],
        tool_status: Literal["running", "done", "failed"] | None = None,
        receipts: list[dict[str, Any]] | None = None,
        detail: str | None = None,
    ) -> None:
        step = steps[index]
        payload: dict[str, Any] = {
            "mock": True,
            "hardware_control": step.kind == "tool",
            "monitor_id": monitor_id,
            "subject": WAKE_UP_SUBJECT,
            "scenario": "wake_up_blanket",
            "phase": step.phase,
            "kind": step.kind,
            "clock": step.clock,
            "title": step.text,
            "detail": detail or step.text,
            "evidence": [],
            "step_index": index + 1,
            "total_steps": len(steps),
            "thread_status": thread_status,
        }
        if step.checks:
            payload["checks"] = list(step.checks)
        if step.plan:
            payload["plan"] = list(step.plan)
        if step.kind == "tool":
            payload["tools"] = (
                receipts
                if receipts is not None
                else [self._pending_receipt(call) for call in step.tools]
            )
            payload["tool_status"] = tool_status or "running"
        await self.publisher.publish(
            DomainEvent(event_type="activity.step", run_id=run_id, payload=payload)
        )

    async def _publish_wake_up_stop_step(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[WakeUpStep],
        stop_index: int,
        *,
        detail: str,
        receipts: list[dict[str, Any]],
    ) -> None:
        await self.publisher.publish(
            DomainEvent(
                event_type="activity.step",
                run_id=run_id,
                payload={
                    "mock": True,
                    "hardware_control": True,
                    "monitor_id": monitor_id,
                    "subject": WAKE_UP_SUBJECT,
                    "scenario": "wake_up_blanket",
                    "phase": "verification",
                    "kind": "tool",
                    "clock": None,
                    "title": "已停止",
                    "detail": detail,
                    "evidence": [],
                    "step_index": stop_index + 1,
                    "total_steps": len(steps),
                    "thread_status": "stopped",
                    "tool_status": "done",
                    "tools": receipts,
                },
            )
        )

    async def _publish_wake_up_failure(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[WakeUpStep],
        index: int,
        *,
        detail: str,
    ) -> None:
        step = steps[index]
        await self.publisher.publish(
            DomainEvent(
                event_type="activity.step",
                run_id=run_id,
                payload={
                    "mock": True,
                    "hardware_control": step.kind == "tool",
                    "monitor_id": monitor_id,
                    "subject": WAKE_UP_SUBJECT,
                    "scenario": "wake_up_blanket",
                    "phase": step.phase,
                    "kind": "narrative",
                    "clock": step.clock,
                    "title": "没有完成",
                    "detail": detail,
                    "evidence": [],
                    "step_index": index + 1,
                    "total_steps": len(steps),
                    "thread_status": "failed",
                },
            )
        )

    # ------------------------------------------------------------------
    # 睡前温度调节场景（原有行为保持不变）

    async def _continue(
        self,
        *,
        run_id: str,
        monitor_id: str,
        steps: list[_ActivityStep],
        step_delay_ms: int,
    ) -> None:
        try:
            for index in range(1, len(steps) - 1):
                if await self._wait(step_delay_ms / 1_000):
                    await self._publish_stopped(run_id, monitor_id, steps)
                    return
                await self._publish_step(run_id, monitor_id, steps, index)
            if self._stop_event.is_set():
                await self._publish_stopped(run_id, monitor_id, steps)
                return
            await self._execute_temperature_action(run_id, monitor_id, steps)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapters may raise vendor errors
            await self._publish_result(
                run_id=run_id,
                monitor_id=monitor_id,
                steps=steps,
                succeeded=False,
                detail=f"真实硬件控制没有完成：{exc}",
                evidence=["目标：蓝色", "未收到有效硬件回执"],
            )
        finally:
            if self._run_id == run_id:
                self._run_id = None

    async def _execute_temperature_action(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[_ActivityStep],
    ) -> None:
        decision = Decision(
            scene="temperature_cooling_demo",
            should_intervene=True,
            reason="模拟温度连续偏高，需要真实显示降温方向",
            confidence=1,
            confirmation="automatic",
            proposed_actions=[
                ActionRequest(
                    capability="set_rgb_indicator",
                    device_id=self.device_id,
                    parameters={"mode": 3},
                )
            ],
        )
        result = await self.workflow.process_observation(
            Observation(
                source="temperature_cooling_demo",
                facts={"simulated_temperature_c": 27.2},
                confidence=1,
            ),
            run_id=run_id,
            proposed_decision=decision,
        )
        if self._stop_event.is_set():
            await self._publish_stopped(run_id, monitor_id, steps)
            return
        action = result.actions[0] if result.actions else None
        if action is not None and action.status is ActionStatus.STOPPED:
            await self._publish_stopped(run_id, monitor_id, steps)
            return
        succeeded = action is not None and action.status is ActionStatus.SUCCEEDED
        await self._publish_result(
            run_id=run_id,
            monitor_id=monitor_id,
            steps=steps,
            succeeded=succeeded,
            detail=(
                "硬件确认三色 LED 为蓝色，本次模拟降温完成。"
                if succeeded
                else (action.reason if action is not None else "没有创建硬件控制动作。")
            ),
            evidence=(
                ["硬件回执：mode 3 / blue", "结果与计划一致"]
                if succeeded
                else ["目标：mode 3 / blue", "真实硬件未确认目标状态"]
            ),
        )

    async def _publish_stopped(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[_ActivityStep],
    ) -> None:
        await self.publisher.publish(
            DomainEvent(
                event_type="activity.step",
                run_id=run_id,
                payload={
                    "mock": True,
                    "hardware_control": False,
                    "monitor_id": monitor_id,
                    "subject": TEMPERATURE_SUBJECT,
                    "scenario": "temperature_cooling",
                    "phase": "verification",
                    "title": "已停止",
                    "detail": "场景已停止，后续步骤不再执行。",
                    "evidence": [],
                    "step_index": len(steps) + 1,
                    "total_steps": len(steps),
                    "thread_status": "stopped",
                },
            )
        )

    async def _publish_result(
        self,
        *,
        run_id: str,
        monitor_id: str,
        steps: list[_ActivityStep],
        succeeded: bool,
        detail: str,
        evidence: list[str],
    ) -> None:
        await self.publisher.publish(
            DomainEvent(
                event_type="activity.step",
                run_id=run_id,
                payload={
                    "mock": True,
                    "hardware_control": True,
                    "monitor_id": monitor_id,
                    "subject": TEMPERATURE_SUBJECT,
                    "scenario": "temperature_cooling",
                    "phase": "verification",
                    "title": "已经完成" if succeeded else "没有完成",
                    "detail": detail,
                    "evidence": evidence,
                    "step_index": len(steps),
                    "total_steps": len(steps),
                    "thread_status": "completed" if succeeded else "failed",
                },
            )
        )

    async def _publish_step(
        self,
        run_id: str,
        monitor_id: str,
        steps: list[_ActivityStep],
        index: int,
    ) -> None:
        step = steps[index]
        completed = index == len(steps) - 1
        await self.publisher.publish(
            DomainEvent(
                event_type="activity.step",
                run_id=run_id,
                payload={
                    "mock": True,
                    "hardware_control": index >= len(steps) - 2,
                    "monitor_id": monitor_id,
                    "subject": TEMPERATURE_SUBJECT,
                    "scenario": "temperature_cooling",
                    "phase": step.phase,
                    "title": step.title,
                    "detail": step.detail,
                    "evidence": step.evidence,
                    "step_index": index + 1,
                    "total_steps": len(steps),
                    "thread_status": "completed" if completed else "running",
                },
            )
        )

    async def close(self) -> None:
        task = self._task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
