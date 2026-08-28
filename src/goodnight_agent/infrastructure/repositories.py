from __future__ import annotations

from typing import Protocol

from goodnight_agent.domain.models import Action, DomainEvent


class ActionRepository(Protocol):
    async def save(self, action: Action) -> None: ...
    async def get(self, action_id: str) -> Action | None: ...


class InMemoryActionRepository:
    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    async def save(self, action: Action) -> None:
        self._actions[action.action_id] = action

    async def get(self, action_id: str) -> Action | None:
        return self._actions.get(action_id)

    async def list(self) -> list[Action]:
        return list(self._actions.values())


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    async def append(self, event: DomainEvent) -> None:
        self._events.append(event)

    async def list(self) -> list[DomainEvent]:
        return list(self._events)
