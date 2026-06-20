from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Awaitable
from uuid import UUID, uuid4
import weakref
import asyncio
from threading import Lock

from tinysoa.eventbus.message import EventMessage
from tinysoa.core.errors import NotFoundError


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


class EventBus(ABC):
    """Abstract event bus interface for pub/sub messaging."""
    
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
        """Get the number of subscribers for a topic."""
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    """In-memory event bus implementation.
    
    Features:
    - Topic-based routing
    - Multiple subscribers per topic
    - Asynchronous delivery
    - Wildcard topic matching (future)
    - Metrics integration
    """
    
    def __init__(self, enable_metrics: bool = True):
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._enable_metrics = enable_metrics
        self._lock = Lock()
        
        # Metrics
        self._published_count = 0
        self._delivered_count = 0
        self._error_count = 0
    
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
                    sub for sub in self._subscribers[subscription.topic]
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
                "total_subscribers": sum(len(subs) for subs in self._subscribers.values()),
            }
    
    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        with self._lock:
            self._published_count = 0
            self._delivered_count = 0
            self._error_count = 0


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
_global_event_bus: Optional[InMemoryEventBus] = None
_bus_lock = Lock()


def get_event_bus() -> InMemoryEventBus:
    """Get the global event bus instance."""
    global _global_event_bus
    if _global_event_bus is None:
        with _bus_lock:
            if _global_event_bus is None:
                _global_event_bus = InMemoryEventBus()
    return _global_event_bus


def set_event_bus(bus: InMemoryEventBus) -> None:
    """Set a custom global event bus (useful for testing)."""
    global _global_event_bus
    with _bus_lock:
        _global_event_bus = bus
