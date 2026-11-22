from __future__ import annotations

from typing import Any, Mapping, Optional

from tinysoa.core.errors import ValidationError

from .bus import EventBus, EventHandler, Subscription
from .message import EventMessage


class TopicPublisher:
    """Application-facing publisher bound to one topic."""

    def __init__(self, bus: EventBus, topic: str):
        if not topic:
            raise ValidationError("TopicPublisher.topic must be non-empty")
        self._bus = bus
        self._topic = topic

    @property
    def topic(self) -> str:
        return self._topic

    async def register(self) -> None:
        """Register the topic with the bus when the transport supports it.

        InMemory/TCP are no-ops; SOME/IP creates and announces the service
        eventgroup so subscribers can discover it before the first publish.
        """
        register = getattr(self._bus, "register_topic", None)
        if register is not None:
            await register(self._topic)

    async def publish(
        self,
        payload: Any,
        *,
        headers: Optional[Mapping[str, str]] = None,
        content_type: str = "application/json",
    ) -> None:
        """Publish a business payload on this topic."""
        await self._bus.publish(
            EventMessage(
                topic=self._topic,
                payload=payload,
                headers=dict(headers or {}),
                content_type=content_type,
            )
        )


class TopicSubscriber:
    """Application-facing subscriber bound to one topic."""

    def __init__(self, bus: EventBus, topic: str):
        if not topic:
            raise ValidationError("TopicSubscriber.topic must be non-empty")
        self._bus = bus
        self._topic = topic

    @property
    def topic(self) -> str:
        return self._topic

    def on(self, handler: EventHandler) -> Subscription:
        """Subscribe an async handler; returns the subscription token."""
        return self._bus.subscribe(self._topic, handler)

    def off(self, subscription: Subscription) -> None:
        """Cancel a subscription."""
        self._bus.unsubscribe(subscription)
