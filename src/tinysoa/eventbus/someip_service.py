from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from tinysoa.api.service_api import MethodSelector
from tinysoa.core.errors import NotFoundError, StateError
from tinysoa.core.model import Message

from .someip import SomeIPEndpoint, SomeIPEventBus, SomeIPTopicMapping
from .someip_method import (
    MethodHandler,
    SomeIPMethodDispatcher,
    SomeIPMethodInvoker,
    SomeIPServiceBinding,
)
from .topic import TopicPublisher, TopicSubscriber


class SomeIPService:
    """Application-facing SOME/IP service facade.

    Owns one endpoint and exposes three application views:

    - ``publisher(topic)`` / ``subscriber(topic)`` for events
    - ``method(name)`` for server-side method handlers
    - ``invoke(method, payload)`` for client-side RPC

    The event bus and method dispatcher share the same endpoint and
    ``SomeIPServiceInstance``, so one service has one SD Offer and one port.
    """

    def __init__(
        self,
        binding: SomeIPServiceBinding,
        *,
        event_mappings: Optional[Mapping[str, SomeIPTopicMapping]] = None,
        local_ip: Optional[str] = None,
        is_publisher: bool = True,
        endpoint: Optional[SomeIPEndpoint] = None,
    ):
        self.binding = binding
        self.local_ip = binding.local_ip if local_ip is None else local_ip
        self.is_publisher = is_publisher
        self._owns_endpoint = endpoint is None
        self._endpoint = endpoint or SomeIPEndpoint(
            local_ip=self.local_ip,
            publisher_port=binding.server_port,
            is_publisher=is_publisher,
            mappings=(event_mappings or {}).values(),
        )
        self._event_bus: Optional[SomeIPEventBus] = None
        if event_mappings:
            self._event_bus = SomeIPEventBus(
                dict(event_mappings),
                local_ip=self.local_ip,
                publisher_port=binding.server_port,
                is_publisher=is_publisher,
                endpoint=self._endpoint,
            )
        self._dispatcher = SomeIPMethodDispatcher(
            binding,
            local_ip=self.local_ip,
            server_port=binding.server_port,
            endpoint=self._endpoint,
        )
        self._invoker: Optional[SomeIPMethodInvoker] = None
        self._publishers: Dict[str, TopicPublisher] = {}
        self._started = False

    @property
    def endpoint(self) -> SomeIPEndpoint:
        return self._endpoint

    @property
    def event_bus(self) -> Optional[SomeIPEventBus]:
        return self._event_bus

    @property
    def dispatcher(self) -> SomeIPMethodDispatcher:
        return self._dispatcher

    @property
    def is_started(self) -> bool:
        return self._started

    def publisher(self, topic: str) -> TopicPublisher:
        """Return (and remember) an event publisher for ``topic``."""
        if self._event_bus is None:
            raise StateError("SomeIPService has no event mappings")
        if topic not in self._event_bus.mappings:
            raise NotFoundError(f"No event mapping for topic: {topic}")
        publisher = self._publishers.get(topic)
        if publisher is None:
            publisher = TopicPublisher(self._event_bus, topic)
            self._publishers[topic] = publisher
        return publisher

    def subscriber(self, topic: str) -> TopicSubscriber:
        """Return an event subscriber for ``topic``."""
        if self._event_bus is None:
            raise StateError("SomeIPService has no event mappings")
        return TopicSubscriber(self._event_bus, topic)

    def method(self, name: str) -> Callable[[MethodHandler], MethodHandler]:
        """Decorator registering a server-side async method handler."""
        return self._dispatcher.method(name)

    def register_method(self, name: str, handler: MethodHandler) -> None:
        """Register a server-side async method handler."""
        self._dispatcher.register(name, handler)

    async def start(self) -> None:
        """Start the shared endpoint, event bus, and registered methods."""
        if self._started:
            return
        if not self._endpoint.started:
            await self._endpoint.start()
        if self._event_bus is not None:
            await self._event_bus.start()
            for publisher in self._publishers.values():
                await publisher.register()
        if self._dispatcher.has_handlers:
            await self._dispatcher.start()
        self._started = True

    async def stop(self) -> None:
        """Stop RPC client, methods, events, and the owned endpoint."""
        if not self._started:
            return
        self._started = False
        if self._invoker is not None:
            await self._invoker.stop()
            self._invoker = None
        await self._dispatcher.stop()
        if self._event_bus is not None:
            await self._event_bus.stop()
        if self._owns_endpoint:
            await self._endpoint.stop()

    async def invoke(
        self,
        method: MethodSelector,
        payload: Any,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Message:
        """Invoke a remote method through the shared endpoint."""
        if not self._started:
            raise StateError("SomeIPService is not started")
        if not self.binding.methods:
            raise NotFoundError("SomeIPService binding has no methods")
        if self._invoker is None:
            self._invoker = SomeIPMethodInvoker(
                self.binding,
                local_ip=self.local_ip,
                local_port=self.binding.local_port,
                endpoint=self._endpoint,
            )
            await self._invoker.start()
        return await self._invoker.invoke(
            self.binding.name,
            method,
            payload,
            headers=headers,
            timeout=timeout,
        )
