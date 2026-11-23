from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import (
    Any,
    Awaitable,
    Callable,
    ClassVar,
    Dict,
    List,
    Mapping,
    Optional,
    Set,
)
from uuid import UUID, uuid4

from tinysoa.core.errors import StateError, ValidationError
from tinysoa.eventbus.message import EventMessage

EventHandler = Callable[[EventMessage], Awaitable[None]]


@dataclass
class Subscription:
    """Represents a subscription to an event topic."""

    id: UUID
    topic: str
    handler: EventHandler

    @staticmethod
    def new(topic: str, handler: EventHandler) -> "Subscription":
        return Subscription(id=uuid4(), topic=topic, handler=handler)


class Topology(str, Enum):
    """Deployment topology of an :class:`EventBus` implementation.

    ``LOCAL``
        In-process only; no transport and no discovery.
    ``BROKER``
        Clients connect through a central broker (e.g. TCP, MQTT).  The
        broker address is configured by the application.
    ``PEER``
        Endpoints exchange messages directly.  Discovery, when present, is a
        protocol concern (SOME/IP SD, DDS RTPS), not an application concern.
    """

    LOCAL = "local"
    BROKER = "broker"
    PEER = "peer"


class EventBus(ABC):
    """Abstract event bus interface for pub/sub messaging.

    The bus owns all registration state.  ``TopicPublisher`` and
    ``TopicSubscriber`` handles are only addresses; registering one with the
    bus is the single control-plane action that makes it active.
    """

    #: Deployment topology; every concrete implementation must declare it.
    topology: ClassVar[Topology]

    def __init__(self) -> None:
        self._registered_publishers: Set[Any] = set()
        self._publisher_topic_refcounts: Dict[str, int] = {}
        self._subscriber_subscriptions: Dict[Any, Subscription] = {}

    def _ensure_registration_state(self) -> None:
        """Initialise registration state for subclasses that skip ``super()``."""
        if not hasattr(self, "_registered_publishers"):
            self._registered_publishers = set()
            self._publisher_topic_refcounts = {}
            self._subscriber_subscriptions = {}

    async def register(self, participant: Any) -> None:
        """Activate a publisher or subscriber on this bus.

        - A publisher becomes allowed to publish its topic.  The first
          registration triggers a protocol hook (SOME/IP announces the service).
        - A subscriber is subscribed and its handler bound in one action.

        Registration is idempotent for the same participant object.
        """
        self._ensure_registration_state()
        if getattr(participant, "bus", None) is not self:
            raise ValidationError("participant is bound to a different bus")

        topic = getattr(participant, "topic", None)
        if not isinstance(topic, str) or not topic:
            raise ValidationError("participant has no valid topic")

        role = getattr(participant, "role", None)
        if role == "publisher":
            if participant in self._registered_publishers:
                return
            self._registered_publishers.add(participant)
            refcount = self._publisher_topic_refcounts.get(topic, 0)
            self._publisher_topic_refcounts[topic] = refcount + 1
            try:
                if refcount == 0:
                    await self._on_publisher_registered(topic)
            except BaseException:
                # Roll back local state even when the hook is cancelled.
                self._registered_publishers.discard(participant)
                if refcount == 0:
                    self._publisher_topic_refcounts.pop(topic, None)
                else:
                    self._publisher_topic_refcounts[topic] = refcount
                raise
            return

        if role == "subscriber":
            if participant in self._subscriber_subscriptions:
                return
            handler = getattr(participant, "handler", None)
            if handler is None or not callable(handler):
                raise ValidationError("subscriber has no callable handler")
            self._subscriber_subscriptions[participant] = self.subscribe(topic, handler)
            return

        raise ValidationError("participant must be a TopicPublisher or TopicSubscriber")

    async def unregister(self, participant: Any) -> None:
        """Deactivate a participant; safe to call more than once."""
        self._ensure_registration_state()
        if participant in self._registered_publishers:
            self._registered_publishers.discard(participant)
            topic = getattr(participant, "topic", "")
            remaining = self._publisher_topic_refcounts.get(topic, 0) - 1
            if remaining > 0:
                self._publisher_topic_refcounts[topic] = remaining
            else:
                self._publisher_topic_refcounts.pop(topic, None)
                await self._on_publisher_unregistered(topic)
            return

        subscription = self._subscriber_subscriptions.pop(participant, None)
        if subscription is not None:
            self.unsubscribe(subscription)

    def is_registered(self, participant: Any) -> bool:
        """Return whether ``participant`` is currently active on this bus."""
        self._ensure_registration_state()
        return (
            participant in self._registered_publishers
            or participant in self._subscriber_subscriptions
        )

    def has_registered_publisher(self, topic: str) -> bool:
        """Return whether at least one publisher is registered for ``topic``."""
        self._ensure_registration_state()
        return self._publisher_topic_refcounts.get(topic, 0) > 0

    async def _on_publisher_registered(self, topic: str) -> None:
        """Protocol hook called when the first publisher for ``topic`` is added."""

    async def _on_publisher_unregistered(self, topic: str) -> None:
        """Protocol hook called when the last publisher for ``topic`` is removed."""

    def _clear_registrations(self) -> None:
        """Drop all bus-owned registration state."""
        self._ensure_registration_state()
        self._registered_publishers.clear()
        self._publisher_topic_refcounts.clear()
        self._subscriber_subscriptions.clear()

    @abstractmethod
    async def publish(self, message: EventMessage) -> None:
        """Publish an event message to the bus."""
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, topic: str, handler: EventHandler) -> Subscription:
        """Subscribe to a topic and return a subscription token."""
        raise NotImplementedError

    @abstractmethod
    def unsubscribe(self, subscription: Subscription) -> None:
        """Unsubscribe using a subscription token."""
        raise NotImplementedError

    @abstractmethod
    def get_subscribers_count(self, topic: str) -> int:
        """Get the number of *local* subscribers for a topic."""
        raise NotImplementedError

    def publisher(self, topic: str) -> "TopicPublisher":
        """Return an application-facing publisher bound to ``topic``."""
        return TopicPublisher(self, topic)

    def subscriber(self, topic: str, handler: EventHandler) -> "TopicSubscriber":
        """Return an application-facing subscriber for ``topic`` and ``handler``."""
        return TopicSubscriber(self, topic, handler)


class TopicPublisher:
    """Application-facing publisher bound to one topic.

    The handle itself has no side effects; call ``await bus.register(publisher)``
    to activate it.  Publishing before registration raises ``StateError``.
    """

    role = "publisher"

    def __init__(self, bus: EventBus, topic: str):
        if not topic:
            raise ValidationError("TopicPublisher.topic must be non-empty")
        self._bus = bus
        self._topic = topic

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def topic(self) -> str:
        return self._topic

    async def publish(
        self,
        payload: Any,
        *,
        headers: Optional[Mapping[str, str]] = None,
        content_type: str = "application/json",
    ) -> None:
        """Publish a business payload on this topic.

        The bus must have registered this publisher first; this keeps the
        control plane (registration) separate from the data plane (publish).
        """
        if not self._bus.is_registered(self):
            raise StateError(
                f"Publisher for topic {self._topic!r} is not registered; "
                "call await bus.register(publisher) first"
            )
        await self._bus.publish(
            EventMessage(
                topic=self._topic,
                payload=payload,
                headers=dict(headers or {}),
                content_type=content_type,
            )
        )


class TopicSubscriber:
    """Application-facing subscriber bound to one topic and one handler.

    Creating the handle has no side effects; ``await bus.register(subscriber)``
    performs the subscription and binds the handler in one bus action.
    """

    role = "subscriber"

    def __init__(self, bus: EventBus, topic: str, handler: EventHandler):
        if not topic:
            raise ValidationError("TopicSubscriber.topic must be non-empty")
        if not callable(handler):
            raise ValidationError("TopicSubscriber.handler must be callable")
        self._bus = bus
        self._topic = topic
        self._handler = handler

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def topic(self) -> str:
        return self._topic

    @property
    def handler(self) -> EventHandler:
        return self._handler


class ManagedEventBus(EventBus):
    """Event bus with an explicit asynchronous lifecycle.

    Transports that open sockets, tasks, or discovery endpoints implement this
    interface so callers can start and stop them uniformly.  ``stop()`` must be
    idempotent and safe to call after a failed ``start()``.
    """

    @abstractmethod
    async def start(self) -> None:
        """Open the transport and make the bus ready for pub/sub."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """Close the transport and release all resources."""
        raise NotImplementedError


class EventBusBroker(ABC):
    """A process-level broker that relays events between EventBus clients.

    Brokers are only used by ``BROKER``-topology buses.  ``start``/``stop`` are
    synchronous because they bootstrap a server process (or an in-process
    helper); request-path operations stay on the :class:`EventBus` interface.
    """

    topology: ClassVar[Topology] = Topology.BROKER

    @abstractmethod
    def start(self) -> None:
        """Bind the broker and begin accepting clients."""
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Stop accepting clients and close all connections."""
        raise NotImplementedError


class TopicMatcher:
    """Helper for topic pattern matching (for future wildcard support)."""

    @staticmethod
    def matches(topic: str, pattern: str) -> bool:
        """Check if a topic matches a pattern.

        Future: support wildcards like 'service.*' or 'service.#'
        Currently: exact match only
        """
        return topic == pattern

    @staticmethod
    def match_any(topic: str, patterns: List[str]) -> bool:
        """Check if topic matches any of the patterns."""
        return any(TopicMatcher.matches(topic, p) for p in patterns)


# Global event bus instance
_global_event_bus: Optional[EventBus] = None
_bus_lock = Lock()


def get_event_bus() -> EventBus:
    """Get the global event bus instance (defaults to in-memory)."""
    global _global_event_bus
    if _global_event_bus is None:
        # Local import avoids a bus <-> memory import cycle.
        from .memory import InMemoryEventBus

        with _bus_lock:
            if _global_event_bus is None:
                _global_event_bus = InMemoryEventBus()
    return _global_event_bus


def set_event_bus(bus: EventBus) -> None:
    """Set a custom global event bus (useful for testing)."""
    global _global_event_bus
    with _bus_lock:
        _global_event_bus = bus
