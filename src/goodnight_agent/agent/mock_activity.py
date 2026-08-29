from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from goodnight_agent.agent.workflow import SimpleWorkflow
from goodnight_agent.domain.models import (
    ActionRequest,
    ActionStatus,
    Decision,
    DomainEvent,
    Observation,
    new_id,
)
from goodnight_agent.infrastructure.events import EventPublisher


class MockActivityRequest(BaseModel):
    scenario: Literal["temperature_cooling"] = "temperature_cooling"
    step_delay_ms: int = Field(default=2_200, ge=500, le=5_000)


class MockActivityStartResult(BaseModel):
    run_id: str
    monitor_id: str
    status: Literal["running"] = "running"
    total_steps: int
    step_delay_ms: int


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


@dataclass
class MockActivitySimulator:
    publisher: EventPublisher
    workflow: SimpleWorkflow
    device_id: str
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _run_id: str | None = field(default=None, init=False)

    async def start(self, request: MockActivityRequest) -> MockActivityStartResult:
        if self._task is not None and not self._task.done():
            raise RuntimeError("a mock activity is already running")

        run_id = new_id("run")
        monitor_id = f"temperature:{new_id('monitor')}"
        steps = _TEMPERATURE_COOLING_STEPS
        self._run_id = run_id
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
            total_steps=len(steps),
            step_delay_ms=request.step_delay_ms,
        )

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
                await asyncio.sleep(step_delay_ms / 1_000)
                await self._publish_step(run_id, monitor_id, steps, index)
            await self._execute_temperature_action(run_id, monitor_id, steps)
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
        action = result.actions[0] if result.actions else None
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
                    "subject": "睡前温度调节",
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
                    "subject": "睡前温度调节",
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
