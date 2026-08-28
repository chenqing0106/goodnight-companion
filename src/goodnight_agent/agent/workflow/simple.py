from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from goodnight_agent.agent.policies import PermissionPolicy, SafetyPolicy
from goodnight_agent.agent.scene_evaluator import SceneEvaluator
from goodnight_agent.agent.verifier import ResultVerifier
from goodnight_agent.agent.world_state import WorldState
from goodnight_agent.devices.base import DeviceGateway
from goodnight_agent.domain.models import (
    Action,
    ActionStatus,
    Decision,
    DeviceCommand,
    DeviceCommandStatus,
    DomainEvent,
    Observation,
    PermissionMode,
    new_id,
)
from goodnight_agent.domain.state_machine import ActionStateMachine
from goodnight_agent.infrastructure.events import EventPublisher
from goodnight_agent.infrastructure.repositories import ActionRepository


class WorkflowResult(BaseModel):
    run_id: str
    observation_id: str
    decision: Decision | None = None
    actions: list[Action] = Field(default_factory=list)


@dataclass
class SimpleWorkflow:
    gateway: DeviceGateway
    publisher: EventPublisher
    actions: ActionRepository
    world_state: WorldState = field(default_factory=WorldState)
    evaluator: SceneEvaluator = field(default_factory=SceneEvaluator)
    permissions: PermissionPolicy = field(default_factory=PermissionPolicy)
    safety: SafetyPolicy = field(default_factory=SafetyPolicy)
    verifier: ResultVerifier = field(default_factory=ResultVerifier)
    machine: ActionStateMachine = field(default_factory=ActionStateMachine)
    command_timeout_ms: int = 30_000
    _command_ids: dict[str, str] = field(default_factory=dict, init=False)
    _action_locks: dict[str, asyncio.Lock] = field(default_factory=dict, init=False)

    async def process_observation(self, observation: Observation) -> WorkflowResult:
        run_id = new_id("run")
        self.world_state.apply_observation(observation)
        await self._publish(
            "observation.updated",
            run_id=run_id,
            payload=observation.model_dump(mode="json"),
        )

        decision = self.evaluator.evaluate(self.world_state)
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
            completed.append(await self._prepare_action(action))

        return WorkflowResult(
            run_id=run_id,
            observation_id=observation.observation_id,
            decision=decision,
            actions=completed,
        )

    async def _prepare_action(self, action: Action) -> Action:
        action = await self._transition(action, ActionStatus.EVALUATING)
        action = await self._transition(action, ActionStatus.CHECKING)

        permission = self.permissions.mode_for(action.capability)
        if permission is PermissionMode.FORBIDDEN:
            action = await self._transition(
                action,
                ActionStatus.SKIPPED,
                reason="该能力未获得执行权限",
                event_type="action.skipped",
            )
            return action

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
            if latest.status in {
                ActionStatus.SUCCEEDED,
                ActionStatus.FAILED,
                ActionStatus.STOPPED,
                ActionStatus.SKIPPED,
            }:
                return latest

            action = await self._transition(
                latest,
                ActionStatus.EXECUTING,
                event_type="action.started",
            )
            command_id = self._command_ids.setdefault(action.action_id, new_id("cmd"))
            command = DeviceCommand(
                command_id=command_id,
                action_id=action.action_id,
                device_id=action.device_id,
                capability=action.capability,
                parameters=action.parameters,
                timeout_ms=self.command_timeout_ms,
            )
            self.world_state.active_action_id = action.action_id

            terminal_received = False
            try:
                async with asyncio.timeout(self.command_timeout_ms / 1000 + 0.25):
                    async for status in self.gateway.execute(command):
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
                        verification = self.verifier.verify(action, self.world_state)
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
        await self.gateway.stop(command_id)
        await self._publish_action(
            "action.stop_requested",
            action,
            command_id=command_id,
            payload={"requested_by": "user"},
        )
        return action

    async def _require_action(self, action_id: str) -> Action:
        action = await self.actions.get(action_id)
        if action is None:
            raise LookupError(f"action {action_id} not found")
        return action

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
