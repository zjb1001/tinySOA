"""Typed control-plane events and a concrete in-process dispatcher.

This is deliberately **not** an EventBus abstraction: internal events have one
delivery mechanism (the current process), so there is no transport to abstract
over.  The module keeps the typed contract (``InternalEvent`` /
``InternalEventType``) and a small dispatcher with no lifecycle, serialization,
persistence, retries, or network behaviour.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from types import MappingProxyType
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Deque,
    Dict,
    List,
    Mapping,
    Optional,
)
from uuid import UUID, uuid4

from tinysoa.core.errors import ValidationError

logger = logging.getLogger(__name__)


class InternalEventType(str, Enum):
    """Control-plane event types (in-process only)."""

    SERVICE_INITIALIZING = "service.initializing"
    SERVICE_READY = "service.ready"
    SERVICE_DEGRADED = "service.degraded"
    SERVICE_UNHEALTHY = "service.unhealthy"
    SERVICE_STOPPING = "service.stopping"
    SERVICE_STOPPED = "service.stopped"
    SERVICE_ERROR = "service.error"
    INSTANCE_DISCOVERED = "instance.discovered"
    INSTANCE_LOST = "instance.lost"
    DEPENDENCY_SATISFIED = "dependency.satisfied"
    DEPENDENCY_LOST = "dependency.lost"
    CONFIG_CHANGED = "config.changed"


@dataclass(frozen=True)
class InternalEvent:
    """Immutable control-plane event.

    ``details`` is frozen into a read-only mapping so subscribers cannot mutate
    shared state by accident.  Events are in-process values; they are never
    serialized or sent over a transport.
    """

    event_type: InternalEventType
    source_service_id: int
    details: Mapping[str, Any] = field(default_factory=dict)
    related_service_id: Optional[int] = None
    related_instance_id: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, InternalEventType):
            raise ValidationError(
                "InternalEvent.event_type must be an InternalEventType"
            )
        if self.source_service_id < 0:
            raise ValidationError("InternalEvent.source_service_id must be >= 0")
        if self.related_service_id is not None and self.related_service_id < 0:
            raise ValidationError("InternalEvent.related_service_id must be >= 0")
        if self.related_instance_id is not None and self.related_instance_id < 0:
            raise ValidationError("InternalEvent.related_instance_id must be >= 0")
        if not isinstance(self.details, Mapping):
            raise ValidationError("InternalEvent.details must be a mapping")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the event for diagnostics or structured logging."""
        return {
            "event_type": self.event_type.value,
            "source_service_id": self.source_service_id,
            "related_service_id": self.related_service_id,
            "related_instance_id": self.related_instance_id,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": str(self.correlation_id),
            "details": dict(self.details),
        }

    @classmethod
    def service_ready(
        cls,
        service_id: int,
        *,
        instance_id: Optional[int] = None,
        **details: Any,
    ) -> "InternalEvent":
        payload = {"status": "running"}
        payload.update(details)
        return cls(
            event_type=InternalEventType.SERVICE_READY,
            source_service_id=service_id,
            related_service_id=service_id,
            related_instance_id=instance_id,
            details=payload,
        )

    @classmethod
    def service_stopped(
        cls,
        service_id: int,
        *,
        instance_id: Optional[int] = None,
        terminated: bool = False,
        **details: Any,
    ) -> "InternalEvent":
        payload = {"status": "terminated" if terminated else "stopped"}
        payload.update(details)
        return cls(
            event_type=InternalEventType.SERVICE_STOPPED,
            source_service_id=service_id,
            related_service_id=service_id,
            related_instance_id=instance_id,
            details=payload,
        )

    @classmethod
    def dependency_satisfied(
        cls,
        service_id: int,
        dependency_service_id: int,
        **details: Any,
    ) -> "InternalEvent":
        payload = {
            "dependent_service": service_id,
            "dependency_service": dependency_service_id,
        }
        payload.update(details)
        return cls(
            event_type=InternalEventType.DEPENDENCY_SATISFIED,
            source_service_id=service_id,
            related_service_id=dependency_service_id,
            details=payload,
        )

    @classmethod
    def dependency_lost(
        cls,
        service_id: int,
        dependency_service_id: int,
        *,
        required: bool = True,
        **details: Any,
    ) -> "InternalEvent":
        payload = {
            "dependent_service": service_id,
            "dependency_service": dependency_service_id,
            "required": required,
        }
        payload.update(details)
        return cls(
            event_type=InternalEventType.DEPENDENCY_LOST,
            source_service_id=service_id,
            related_service_id=dependency_service_id,
            details=payload,
        )

    @classmethod
    def instance_discovered(
        cls,
        service_id: int,
        instance_id: int,
        **details: Any,
    ) -> "InternalEvent":
        payload = {"instance_id": instance_id}
        payload.update(details)
        return cls(
            event_type=InternalEventType.INSTANCE_DISCOVERED,
            source_service_id=service_id,
            related_service_id=service_id,
            related_instance_id=instance_id,
            details=payload,
        )

    @classmethod
    def instance_lost(
        cls,
        service_id: int,
        instance_id: int,
        *,
        reason: str = "ttl_expired",
        **details: Any,
    ) -> "InternalEvent":
        payload = {"instance_id": instance_id, "reason": reason}
        payload.update(details)
        return cls(
            event_type=InternalEventType.INSTANCE_LOST,
            source_service_id=service_id,
            related_service_id=service_id,
            related_instance_id=instance_id,
            details=payload,
        )


InternalEventHandler = Callable[[InternalEvent], Awaitable[None]]


@dataclass(frozen=True)
class InternalSubscription:
    """Handle returned by :meth:`InternalEventDispatcher.subscribe`."""

    id: UUID
    event_type: InternalEventType
    handler: InternalEventHandler


class InternalEventDispatcher:
    """Concrete, typed, in-process control-plane event dispatcher.

    Semantics:

    - handlers run sequentially in subscription order;
    - a handler exception is logged and never interrupts other handlers;
    - a bounded history is kept for diagnostics;
    - no serialization, persistence, retries, transport, or start/stop.

    The dispatcher is single-event-loop oriented.  A lock guards subscription
    state for callers that also publish from worker threads, but handlers always
    run on the loop that calls :meth:`publish`.
    """

    def __init__(self, history_size: int = 10_000) -> None:
        if history_size < 1:
            raise ValidationError("InternalEventDispatcher.history_size must be >= 1")
        self._history: Deque[InternalEvent] = deque(maxlen=history_size)
        self._subscribers: Dict[InternalEventType, List[InternalSubscription]] = (
            defaultdict(list)
        )
        self._lock = Lock()

    def subscribe(
        self,
        event_type: InternalEventType,
        handler: InternalEventHandler,
    ) -> InternalSubscription:
        """Subscribe ``handler`` to one event type."""
        if not isinstance(event_type, InternalEventType):
            raise ValidationError(
                "InternalEventDispatcher.subscribe event_type must be an "
                "InternalEventType"
            )
        if not callable(handler):
            raise ValidationError(
                "InternalEventDispatcher.subscribe handler must be callable"
            )
        subscription = InternalSubscription(
            id=uuid4(), event_type=event_type, handler=handler
        )
        with self._lock:
            self._subscribers[event_type].append(subscription)
        return subscription

    def unsubscribe(self, subscription: InternalSubscription) -> None:
        """Remove a subscription; safe to call more than once."""
        with self._lock:
            subscriptions = self._subscribers.get(subscription.event_type)
            if not subscriptions:
                return
            remaining = [
                candidate
                for candidate in subscriptions
                if candidate.id != subscription.id
            ]
            if remaining:
                self._subscribers[subscription.event_type] = remaining
            else:
                self._subscribers.pop(subscription.event_type, None)

    async def publish(self, event: InternalEvent) -> None:
        """Append to history and deliver to subscribers in subscription order."""
        if not isinstance(event, InternalEvent):
            raise ValidationError("InternalEventDispatcher.publish expects an event")
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers.get(event.event_type, ()))
        for subscription in subscribers:
            await self._invoke(subscription, event)

    def history(
        self,
        event_type: Optional[InternalEventType] = None,
        limit: int = 100,
    ) -> List[InternalEvent]:
        """Return up to ``limit`` most recent events, optionally filtered."""
        if limit < 1:
            return []
        with self._lock:
            events = list(self._history)
        if event_type is not None:
            events = [event for event in events if event.event_type is event_type]
        return events[-limit:]

    def subscriber_count(self, event_type: Optional[InternalEventType] = None) -> int:
        """Return the number of subscribers for one type or all types."""
        with self._lock:
            if event_type is None:
                return sum(len(items) for items in self._subscribers.values())
            return len(self._subscribers.get(event_type, ()))

    async def subscribe_async_iter(
        self, event_type: InternalEventType
    ) -> AsyncIterator[InternalEvent]:
        """Yield events of ``event_type`` until the consumer stops iterating.

        Call ``aclose()`` on the iterator (for example via
        ``contextlib.aclosing``) to unsubscribe deterministically instead of
        waiting for garbage collection.
        """
        queue: asyncio.Queue[InternalEvent] = asyncio.Queue()

        async def handler(event: InternalEvent) -> None:
            await queue.put(event)

        subscription = self.subscribe(event_type, handler)
        try:
            while True:
                yield await queue.get()
        finally:
            self.unsubscribe(subscription)

    async def _invoke(
        self, subscription: InternalSubscription, event: InternalEvent
    ) -> None:
        try:
            await subscription.handler(event)
        except Exception:
            logger.exception(
                "internal event handler failed: type=%s source=%#x",
                event.event_type.value,
                event.source_service_id,
            )
