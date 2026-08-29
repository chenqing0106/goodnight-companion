from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from goodnight_agent.agent.policies import PermissionPolicy, SafetyPolicy
from goodnight_agent.agent.scene_evaluator import SceneEvaluator
from goodnight_agent.agent.verifier import ResultVerifier
from goodnight_agent.agent.world_state import WorldState
from goodnight_agent.devices.base import DeviceGateway
from goodnight_agent.devices.registry import DeviceRegistry
from goodnight_agent.domain.models import (
    Action,
    ActionStatus,
    Decision,
    DeviceCommandStatus,
    DomainEvent,
    Observation,
    PermissionMode,
    new_id,
)
from goodnight_agent.domain.state_machine import ActionStateMachine
from goodnight_agent.infrastructure.events import EventPublisher
from goodnight_agent.infrastructure.repositories import ActionRepository
from goodnight_agent.tools.executor import ToolExecutor
from goodnight_agent.tools.registry import ToolError, build_default_tool_registry


class WorkflowResult(BaseModel):
    run_id: str
    observation_id: str
    decision: Decision | None = None
    actions: list[Action] = Field(default_factory=list)


class RunStopResult(BaseModel):
    run_id: str
    status: Literal["stop_requested", "stopped", "completed"]
    actions: list[Action] = Field(default_factory=list)


TERMINAL_ACTION_STATUSES = {
    ActionStatus.SUCCEEDED,
    ActionStatus.FAILED,
    ActionStatus.STOPPED,
    ActionStatus.SKIPPED,
}


@dataclass
class SimpleWorkflow:
    gateway: DeviceGateway
    publisher: EventPublisher
    actions: ActionRepository
    registry: DeviceRegistry | None = None
    tool_executor: ToolExecutor | None = None
    world_state: WorldState = field(default_factory=WorldState)
    evaluator: SceneEvaluator = field(default_factory=SceneEvaluator)
    permissions: PermissionPolicy = field(default_factory=PermissionPolicy)
    safety: SafetyPolicy = field(default_factory=SafetyPolicy)
    verifier: ResultVerifier = field(default_factory=ResultVerifier)
    machine: ActionStateMachine = field(default_factory=ActionStateMachine)
    command_timeout_ms: int = 30_000
    _command_ids: dict[str, str] = field(default_factory=dict, init=False)
    _action_locks: dict[str, asyncio.Lock] = field(default_factory=dict, init=False)
    _cancelled_runs: set[str] = field(default_factory=set, init=False)
    _stopped_runs: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if self.tool_executor is None:
            self.tool_executor = ToolExecutor(
                registry=build_default_tool_registry(),
                gateway=self.gateway,
            )

    async def process_observation(
        self,
        observation: Observation,
        *,
        run_id: str | None = None,
        proposed_decision: Decision | None = None,
    ) -> WorkflowResult:
        run_id = run_id or new_id("run")
        self.world_state.apply_observation(observation)
        await self._publish(
            "observation.updated",
            run_id=run_id,
            payload=observation.model_dump(mode="json"),
        )

        decision = proposed_decision or self.evaluator.evaluate(self.world_state)
        if decision is None:
            await self._publish(
                "decision.skipped",
                run_id=run_id,
                payload={"reason": "当前观察没有触发已实现的睡眠场景"},
            )
            return WorkflowResult(run_id=run_id, observation_id=observation.observation_id)

        await self._publish(
            "decision.created",
            run_id=run_id,
            payload=decision.model_dump(mode="json"),
        )
        if not decision.should_intervene:
            return WorkflowResult(
                run_id=run_id,
                observation_id=observation.observation_id,
                decision=decision,
            )

        created: list[Action] = []
        for request in decision.proposed_actions:
            action = Action(
                run_id=run_id,
                capability=request.capability,
                device_id=request.device_id,
                parameters=request.parameters,
            )
            await self.actions.save(action)
            await self._publish_action("action.created", action)
            created.append(action)

        completed: list[Action] = []
        for action in created:
            latest = await self._require_action(action.action_id)
            if self._run_is_cancelled(run_id):
                completed.append(await self._cancel_before_execution(latest))
            else:
                completed.append(await self._prepare_action(latest))

        await self._publish_run_stopped_if_complete(run_id)

        return WorkflowResult(
            run_id=run_id,
            observation_id=observation.observation_id,
            decision=decision,
            actions=completed,
        )

    async def _prepare_action(self, action: Action) -> Action:
        if self._run_is_cancelled(action.run_id):
            return await self._cancel_before_execution(action)

        action = await self._transition(action, ActionStatus.EVALUATING)
        if self._run_is_cancelled(action.run_id):
            return await self._cancel_before_execution(action)

        action = await self._transition(action, ActionStatus.CHECKING)
        if self._run_is_cancelled(action.run_id):
            return await self._cancel_before_execution(action)

        executor = self._require_tool_executor()
        try:
            executor.validate_action(action)
        except ToolError as exc:
            return await self._transition(
                action,
                ActionStatus.FAILED,
                reason=str(exc),
                error_code="TOOL_VALIDATION_FAILED",
                event_type="action.failed",
            )

        permission = self.permissions.mode_for(action.capability)
        if permission is PermissionMode.FORBIDDEN:
            action = await self._transition(
                action,
                ActionStatus.SKIPPED,
                reason="该能力未获得执行权限",
                event_type="action.skipped",
            )
            return action

        await self._sync_device_registry(action)
        if self._run_is_cancelled(action.run_id):
            return await self._cancel_before_execution(action)

        safety = self.safety.check(action, self.world_state)
        await self._publish_action(
            "safety.checked",
            action,
            payload=safety.model_dump(mode="json"),
        )
        if self._run_is_cancelled(action.run_id):
            return await self._cancel_before_execution(action)

        if not safety.allowed:
            return await self._transition(
                action,
                ActionStatus.FAILED,
                reason=safety.reason,
                error_code="SAFETY_CHECK_FAILED",
                event_type="action.failed",
            )

        if permission is PermissionMode.ASK:
            return await self._transition(
                action,
                ActionStatus.WAITING_CONFIRMATION,
                reason="等待用户确认",
                event_type="action.confirmation_required",
            )

        return await self._execute_action(action)

    async def confirm(self, action_id: str) -> Action:
        action = await self._require_action(action_id)
        if action.status is not ActionStatus.WAITING_CONFIRMATION:
            raise ValueError(f"action {action_id} is not waiting for confirmation")
        await self._sync_device_registry(action)
        safety = self.safety.check(action, self.world_state)
        await self._publish_action(
            "safety.checked",
            action,
            payload=safety.model_dump(mode="json"),
        )
        if not safety.allowed:
            return await self._transition(
                action,
                ActionStatus.FAILED,
                reason=safety.reason,
                error_code="SAFETY_CHECK_FAILED",
                event_type="action.failed",
            )
        return await self._execute_action(action)

    async def _execute_action(self, action: Action) -> Action:
        lock = self._action_locks.setdefault(action.action_id, asyncio.Lock())
        async with lock:
            latest = await self._require_action(action.action_id)
            if latest.status in TERMINAL_ACTION_STATUSES:
                return latest
            if self._run_is_cancelled(latest.run_id):
                return await self._cancel_before_execution(latest)

            executor = self._require_tool_executor()
            command_id = self._command_ids.setdefault(action.action_id, new_id("cmd"))
            try:
                tool_call = executor.prepare_call(latest, command_id)
            except ToolError as exc:
                return await self._transition(
                    latest,
                    ActionStatus.FAILED,
                    reason=str(exc),
                    error_code="TOOL_VALIDATION_FAILED",
                    event_type="action.failed",
                )

            action = await self._transition(
                latest,
                ActionStatus.EXECUTING,
                event_type="action.started",
            )
            definition = executor.registry.require(tool_call.tool_name).definition
            await self._publish_action(
                "tool.called",
                action,
                command_id=command_id,
                payload={
                    "tool_call": tool_call.model_dump(mode="json"),
                    "tool": definition.model_dump(mode="json"),
                },
            )
            self.world_state.active_action_id = action.action_id

            terminal_received = False
            try:
                async with asyncio.timeout(self.command_timeout_ms / 1000 + 0.25):
                    async for status in executor.execute(
                        tool_call,
                        timeout_ms=self.command_timeout_ms,
                    ):
                        await self._publish_action(
                            "action.progress",
                            action,
                            command_id=command_id,
                            payload=status.model_dump(mode="json"),
                        )
                        if not status.status.terminal:
                            continue

                        terminal_received = True
                        if status.status is DeviceCommandStatus.STOPPED:
                            return await self._transition(
                                action,
                                ActionStatus.STOPPED,
                                reason=status.message or "动作已停止",
                                event_type="action.stopped",
                                command_id=command_id,
                            )
                        if status.status is DeviceCommandStatus.FAILED:
                            return await self._transition(
                                action,
                                ActionStatus.FAILED,
                                reason=status.message or "设备执行失败",
                                error_code=status.error_code or "DEVICE_FAILED",
                                event_type="action.failed",
                                command_id=command_id,
                            )

                        result_facts = status.result.get("facts", {})
                        if isinstance(result_facts, dict):
                            self.world_state.apply_result_facts(result_facts)
                        action = await self._transition(action, ActionStatus.VERIFYING)
                        verification = self.verifier.verify(
                            action,
                            self.world_state,
                            status.result,
                        )
                        if verification.verified:
                            return await self._transition(
                                action,
                                ActionStatus.SUCCEEDED,
                                reason=verification.reason,
                                event_type="action.succeeded",
                                command_id=command_id,
                            )
                        return await self._transition(
                            action,
                            ActionStatus.FAILED,
                            reason=verification.reason,
                            error_code="VERIFICATION_FAILED",
                            event_type="action.failed",
                            command_id=command_id,
                        )
            except TimeoutError:
                return await self._transition(
                    action,
                    ActionStatus.FAILED,
                    reason="等待设备结果超时",
                    error_code="DEVICE_TIMEOUT",
                    event_type="action.failed",
                    command_id=command_id,
                )
            except Exception as exc:  # noqa: BLE001 - adapters may raise vendor-specific errors
                return await self._transition(
                    action,
                    ActionStatus.FAILED,
                    reason=f"设备网关异常: {exc}",
                    error_code="DEVICE_GATEWAY_ERROR",
                    event_type="action.failed",
                    command_id=command_id,
                )
            finally:
                if self.world_state.active_action_id == action.action_id:
                    self.world_state.active_action_id = None

            if not terminal_received:
                return await self._transition(
                    action,
                    ActionStatus.FAILED,
                    reason="设备状态流提前结束",
                    error_code="DEVICE_STREAM_ENDED",
                    event_type="action.failed",
                    command_id=command_id,
                )
            return action

    async def stop(self, action_id: str) -> Action:
        action = await self._require_action(action_id)
        if action.status is ActionStatus.WAITING_CONFIRMATION:
            return await self._transition(
                action,
                ActionStatus.STOPPED,
                reason="用户取消了待确认动作",
                event_type="action.stopped",
            )
        if action.status is not ActionStatus.EXECUTING:
            raise ValueError(f"action {action_id} cannot be stopped from {action.status}")

        command_id = self._command_ids.get(action_id)
        if command_id is None:
            raise RuntimeError(f"action {action_id} has no device command")
        await self._require_tool_executor().stop(command_id)
        await self._publish_action(
            "action.stop_requested",
            action,
            command_id=command_id,
            payload={"requested_by": "user"},
        )
        return action

    async def stop_run(self, run_id: str) -> RunStopResult:
        run_actions = await self._list_run_actions(run_id)
        if not run_actions:
            raise LookupError(f"run {run_id} not found")

        if run_id in self._cancelled_runs:
            await self._publish_run_stopped_if_complete(run_id)
            updated = await self._list_run_actions(run_id)
            return RunStopResult(
                run_id=run_id,
                status="stopped" if run_id in self._stopped_runs else "stop_requested",
                actions=updated,
            )

        if all(action.status in TERMINAL_ACTION_STATUSES for action in run_actions):
            return RunStopResult(
                run_id=run_id,
                status="completed",
                actions=run_actions,
            )

        self._cancelled_runs.add(run_id)
        await self._publish(
            "run.stop_requested",
            run_id=run_id,
            payload={"requested_by": "user"},
        )

        for action in run_actions:
            latest = await self._require_action(action.action_id)
            if latest.status in {
                ActionStatus.WAITING_CONFIRMATION,
                ActionStatus.EXECUTING,
            }:
                try:
                    await self.stop(latest.action_id)
                except ValueError:
                    refreshed = await self._require_action(latest.action_id)
                    if refreshed.status not in TERMINAL_ACTION_STATUSES:
                        raise

        await self._publish_run_stopped_if_complete(run_id)
        updated = await self._list_run_actions(run_id)
        return RunStopResult(
            run_id=run_id,
            status="stopped" if run_id in self._stopped_runs else "stop_requested",
            actions=updated,
        )

    def _run_is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled_runs

    async def _cancel_before_execution(self, action: Action) -> Action:
        latest = await self._require_action(action.action_id)
        if latest.status in TERMINAL_ACTION_STATUSES:
            return latest
        if latest.status is ActionStatus.WAITING_CONFIRMATION:
            return await self._transition(
                latest,
                ActionStatus.STOPPED,
                reason="用户停止了整个流程",
                event_type="action.stopped",
            )
        if latest.status in {
            ActionStatus.PENDING,
            ActionStatus.EVALUATING,
            ActionStatus.CHECKING,
        }:
            return await self._transition(
                latest,
                ActionStatus.SKIPPED,
                reason="流程已被用户停止，后续动作不再执行",
                event_type="action.skipped",
            )
        return latest

    async def _list_run_actions(self, run_id: str) -> list[Action]:
        return [action for action in await self.actions.list() if action.run_id == run_id]

    async def _publish_run_stopped_if_complete(self, run_id: str) -> None:
        if run_id not in self._cancelled_runs or run_id in self._stopped_runs:
            return
        actions = await self._list_run_actions(run_id)
        if not actions or any(action.status not in TERMINAL_ACTION_STATUSES for action in actions):
            return

        self._stopped_runs.add(run_id)
        await self._publish(
            "run.stopped",
            run_id=run_id,
            payload={"actions": {action.action_id: action.status.value for action in actions}},
        )

    async def _require_action(self, action_id: str) -> Action:
        action = await self.actions.get(action_id)
        if action is None:
            raise LookupError(f"action {action_id} not found")
        return action

    def _require_tool_executor(self) -> ToolExecutor:
        if self.tool_executor is None:
            raise RuntimeError("tool executor is not configured")
        return self.tool_executor

    async def _sync_device_registry(self, action: Action) -> None:
        if self.registry is None:
            return
        try:
            record = await self.registry.get_device(action.device_id)
        except Exception as exc:  # noqa: BLE001 - adapters may raise vendor-specific errors
            self.world_state.apply_device_record(action.device_id, None)
            await self._publish_action(
                "device.registry_failed",
                action,
                payload={"error": str(exc)},
            )
            return

        self.world_state.apply_device_record(action.device_id, record)
        await self._publish_action(
            "device.registry_synced",
            action,
            payload={
                "device": (
                    record.model_dump(mode="json")
                    if record is not None
                    else {
                        "device_id": action.device_id,
                        "availability": "unknown",
                        "capabilities": [],
                        "capabilities_known": False,
                    }
                )
            },
        )

    async def _transition(
        self,
        action: Action,
        target: ActionStatus,
        *,
        reason: str | None = None,
        error_code: str | None = None,
        event_type: str | None = None,
        command_id: str | None = None,
    ) -> Action:
        updated = self.machine.transition(
            action,
            target,
            reason=reason,
            error_code=error_code,
        )
        await self.actions.save(updated)
        await self._publish_action(
            event_type or "action.status_changed",
            updated,
            command_id=command_id,
            payload={"previous_status": action.status, "status": updated.status},
        )
        return updated

    async def _publish_action(
        self,
        event_type: str,
        action: Action,
        *,
        command_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        body: dict[str, object] = {
            "capability": action.capability,
            "device_id": action.device_id,
            "status": action.status,
        }
        if payload:
            body.update(payload)
        await self._publish(
            event_type,
            run_id=action.run_id,
            action_id=action.action_id,
            command_id=command_id,
            payload=body,
        )

    async def _publish(
        self,
        event_type: str,
        *,
        run_id: str | None = None,
        action_id: str | None = None,
        command_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        await self.publisher.publish(
            DomainEvent(
                event_type=event_type,
                run_id=run_id,
                action_id=action_id,
                command_id=command_id,
                payload=payload or {},
            )
        )
