from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from goodnight_agent.domain.models import Action, Observation

if TYPE_CHECKING:
    from goodnight_agent.agent.workflow.simple import WorkflowResult


class AgentWorkflow(Protocol):
    async def process_observation(self, observation: Observation) -> WorkflowResult: ...

    async def confirm(self, action_id: str) -> Action: ...

    async def stop(self, action_id: str) -> Action: ...
