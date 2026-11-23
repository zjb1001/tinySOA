"""In-process event bus implementation."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Dict, List

from .bus import EventHandler, ManagedEventBus, Subscription, Topology
from .message import EventMessage


class InMemoryEventBus(ManagedEventBus):
    """In-memory event bus implementation.

    Topology ``LOCAL``: no transport, no broker.  ``start`` and ``stop`` are
    no-ops that exist so callers can treat every managed bus uniformly.

    Features:
    - Topic-based routing
    - Multiple subscribers per topic
    - Asynchronous delivery
    - Wildcard topic matching (future)
    - Metrics integration
    """

    topology = Topology.LOCAL

    def __init__(self, enable_metrics: bool = True):
        super().__init__()
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._enable_metrics = enable_metrics
        self._lock = Lock()

        # Metrics
        self._published_count = 0
        self._delivered_count = 0
        self._error_count = 0

    async def start(self) -> None:
        """No-op: the in-memory bus has no transport to open."""

    async def stop(self) -> None:
        """Release subscriptions and registrations."""
        self.clear_all_subscriptions()
        self._clear_registrations()

    async def publish(self, message: EventMessage) -> None:
        """Publish a message to all subscribers of its topic."""
        subscribers = list(self._subscribers.get(message.topic, []))
        self._published_count += 1

        # Deliver to all subscribers
        for subscription in subscribers:
            try:
                await subscription.handler(message)
                if self._enable_metrics:
                    self._delivered_count += 1
            except Exception as e:
                # Log error but don't fail entire publish
                if self._enable_metrics:
                    self._error_count += 1
                # In production, would log this properly
                print(f"Error delivering message to subscriber: {e}")

    def subscribe(self, topic: str, handler: EventHandler) -> Subscription:
        """Subscribe to a topic."""
        subscription = Subscription.new(topic, handler)

        with self._lock:
            self._subscribers[topic].append(subscription)

        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        """Unsubscribe from a topic."""
        with self._lock:
            if subscription.topic in self._subscribers:
                self._subscribers[subscription.topic] = [
                    sub
                    for sub in self._subscribers[subscription.topic]
                    if sub.id != subscription.id
                ]

                # Clean up empty topic lists
                if not self._subscribers[subscription.topic]:
                    del self._subscribers[subscription.topic]

    def get_subscribers_count(self, topic: str) -> int:
        """Get number of subscribers for a topic."""
        with self._lock:
            return len(self._subscribers.get(topic, []))

    def get_all_topics(self) -> List[str]:
        """Get all topics with active subscriptions."""
        with self._lock:
            return list(self._subscribers.keys())

    def clear_all_subscriptions(self) -> None:
        """Remove all subscriptions (useful for testing)."""
        with self._lock:
            self._subscribers.clear()

    def get_metrics(self) -> Dict[str, int]:
        """Get event bus metrics."""
        with self._lock:
            return {
                "published": self._published_count,
                "delivered": self._delivered_count,
                "errors": self._error_count,
                "topics": len(self._subscribers),
                "total_subscribers": sum(
                    len(subs) for subs in self._subscribers.values()
                ),
            }

    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        with self._lock:
            self._published_count = 0
            self._delivered_count = 0
            self._error_count = 0
