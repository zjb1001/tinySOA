from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Union, Any, Awaitable
from uuid import UUID, uuid4

from tinysoa.core.model import Service, Event, Message

ServiceSelector = Union[int, str, Service]
EventSelector = Union[int, str, Event]

EventHandler = Callable[[Message], Awaitable[None]]


@dataclass(frozen=True)
class Subscription:
    id: UUID
    service_id: int
    event_id: int

    @staticmethod
    def new(service_id: int, event_id: int) -> "Subscription":
        return Subscription(id=uuid4(), service_id=service_id, event_id=event_id)


class EventPublisher(ABC):
    """Publisher interface for emitting events."""

    @abstractmethod
    async def publish(
        self,
        service: ServiceSelector,
        event: EventSelector,
        payload: Any | Message,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        """Publish an event; implementations decide synchronous/async semantics."""
        raise NotImplementedError


class EventSubscriber(ABC):
    """Subscriber interface for event consumption."""

    @abstractmethod
    def subscribe(
        self,
        service: ServiceSelector,
        event: EventSelector,
        handler: EventHandler,
    ) -> Subscription:
        """Subscribe to an event and return a subscription token."""
        raise NotImplementedError

    @abstractmethod
    def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel a subscription by token."""
        raise NotImplementedError
