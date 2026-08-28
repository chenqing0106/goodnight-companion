from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from goodnight_agent.domain.models import DomainEvent


class EventPublisher(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...


class InMemoryEventPublisher:
    def __init__(self, max_history: int = 500) -> None:
        self.max_history = max_history
        self.events: list[DomainEvent] = []
        self._subscribers: set[asyncio.Queue[DomainEvent]] = set()

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
        if len(self.events) > self.max_history:
            del self.events[: len(self.events) - self.max_history]
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)

    def recent(self, *, limit: int = 100, run_id: str | None = None) -> list[DomainEvent]:
        events = self.events
        if run_id is not None:
            events = [event for event in events if event.run_id == run_id]
        return list(events[-limit:])

    async def subscribe(self) -> AsyncIterator[DomainEvent]:
        queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
