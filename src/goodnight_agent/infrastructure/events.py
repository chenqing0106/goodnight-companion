from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from goodnight_agent.domain.models import DomainEvent


class EventPublisher(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []
        self._subscribers: set[asyncio.Queue[DomainEvent]] = set()

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[DomainEvent]:
        queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
