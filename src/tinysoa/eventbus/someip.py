from __future__ import annotations

import asyncio
import json
import logging
import socket
from dataclasses import dataclass
from threading import Lock
from typing import (
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

from someip.config import Eventgroup
from someip.header import _T_SOCKNAME, L4Protocols, SOMEIPHeader, SOMEIPMessageType
from someip.sd import (
    DatagramProtocolAdapter,
    ServiceDiscoveryProtocol,
    SOMEIPDatagramProtocol,
)

# Import pysomeip components
from someip.service import SimpleEventgroup, SimpleService

from tinysoa.core.errors import NotFoundError, StateError
from tinysoa.eventbus.bus import (
    EventHandler,
    ManagedEventBus,
    Subscription,
    Topology,
)
from tinysoa.eventbus.message import EventMessage

# Global port allocator for multi-publisher scenarios
_PORT_LOCK = Lock()
_NEXT_PORT = 30490
_ALLOCATED_PORTS: Dict[Tuple[int, int], int] = {}

# Global subscription sequence control
_SUBSCRIPTION_LOCK = Lock()
_SUBSCRIPTION_COUNTER = 0


def _get_service_port(service_id: int, instance_id: int, base_port: int = 30490) -> int:
    """
    Allocate a unique port for a (service_id, instance_id) pair.
    Honors the provided base_port per process, avoiding fixed 30490 conflicts.
    """
    global _NEXT_PORT, _ALLOCATED_PORTS

    key = (service_id, instance_id)

    with _PORT_LOCK:
        if key in _ALLOCATED_PORTS:
            return _ALLOCATED_PORTS[key]

        # Ensure we start at least from base_port for this process
        if _NEXT_PORT < base_port:
            _NEXT_PORT = base_port

        port = _NEXT_PORT
        _ALLOCATED_PORTS[key] = port
        _NEXT_PORT = port + 1

        return port


@dataclass
class SomeIPTopicMapping:
    """Mapping configuration for a topic to SOME/IP identifiers."""

    service_id: int
    instance_id: int
    eventgroup_id: int
    major_version: int = 1
    minor_version: int = 0
    event_id: int = 0x0001  # Default event ID within the group
    l4_protocol: str = "UDP"  # UDP or TCP


class SomeIPEventgroupAdapter(SimpleEventgroup):
    """
    Adapter that bridges tinySOA EventBus handlers with SOME/IP EventGroups.
    Wraps handler invocations and message deserialization.
    """

    def __init__(
        self,
        service: SimpleService,
        eventgroup_id: int,
        on_notification: Callable[[bytes], Awaitable[None]],
        interval: Optional[float] = 0.5,
    ):
        super().__init__(service, id=eventgroup_id, interval=interval)
        self.on_notification = on_notification

    async def handle_notification(self, payload: bytes) -> None:
        """Called when a notification is received."""
        await self.on_notification(payload)


class SomeIPServiceInstance:
    """One pysomeip SimpleService endpoint for a (service_id, instance_id).

    Eventgroups and methods registered here share one unicast endpoint and one
    SD Offer, which is required for SOME/IP fields (getter/setter + notifier).
    """

    def __init__(
        self,
        service_id: int,
        instance_id: int,
        major_version: int,
        local_addr: str,
        port: int,
        minor_version: int = 0,
    ):
        self.service_id = service_id
        self.instance_id = instance_id
        self.major_version = major_version
        self.minor_version = minor_version
        self.local_addr = local_addr
        self.port = port
        self.logger = logging.getLogger(__name__)
        self._service: Optional[SimpleService] = None
        self._eventgroups: Dict[int, SomeIPEventgroupAdapter] = {}
        self._pending_eventgroups: List[
            Tuple[int, Callable[[bytes], Awaitable[None]]]
        ] = []
        self._methods: Dict[int, Callable] = {}
        self._pending_methods: List[Tuple[int, Callable]] = []

    @property
    def service(self) -> Optional[SimpleService]:
        """The underlying pysomeip service (available after ``start``)."""
        return self._service

    @property
    def started(self) -> bool:
        return self._service is not None

    def add_eventgroup(
        self, eventgroup_id: int, on_notification: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """Queue or register an eventgroup before/after ``start``."""
        if self._service is not None:
            self.register_eventgroup(eventgroup_id, on_notification)
            return
        self._pending_eventgroups.append((eventgroup_id, on_notification))

    def register_eventgroup(
        self, eventgroup_id: int, on_notification: Callable[[bytes], Awaitable[None]]
    ) -> SomeIPEventgroupAdapter:
        """Register an eventgroup on a started service."""
        if self._service is None:
            raise RuntimeError("Service not started")
        existing = self._eventgroups.get(eventgroup_id)
        if existing is not None:
            return existing
        adapter = SomeIPEventgroupAdapter(
            self._service, eventgroup_id, on_notification, interval=0.5
        )
        self._service.register_eventgroup(adapter)
        self._eventgroups[eventgroup_id] = adapter
        self.logger.debug(
            "Registered eventgroup %#06x on service %#06x:%#06x",
            eventgroup_id,
            self.service_id,
            self.instance_id,
        )
        return adapter

    def register_method(self, method_id: int, handler: Callable) -> None:
        """Register a SOME/IP method handler (sync pysomeip callback)."""
        if method_id in self._methods:
            raise ValueError(f"Method {method_id:#x} already registered")
        self._methods[method_id] = handler
        if self._service is not None:
            self._service.register_method(method_id, handler)
        else:
            self._pending_methods.append((method_id, handler))

    async def start(self, announcer) -> None:
        """Create the unicast endpoint, register methods/eventgroups, announce."""
        if self._service is not None:
            return
        ServiceClass = type(
            f"Service_{self.service_id:04x}_{self.instance_id:04x}",
            (SimpleService,),
            {
                "service_id": self.service_id,
                "version_major": self.major_version,
                "version_minor": self.minor_version,
            },
        )
        try:
            _trsp, prot = await ServiceClass.create_unicast_endpoint(  # type: ignore[attr-defined]
                instance_id=self.instance_id, local_addr=(self.local_addr, self.port)
            )
            self._service = prot
        except OSError as e:
            self.logger.error(
                "Failed to bind service to %s:%d: %s",
                self.local_addr,
                self.port,
                e,
            )
            raise

        for method_id, handler in self._pending_methods:
            self._service.register_method(method_id, handler)
        self._pending_methods.clear()

        for eg_id, cb in self._pending_eventgroups:
            self.register_eventgroup(eg_id, cb)
        self._pending_eventgroups.clear()

        try:
            if announcer is not None:
                self._service.start_announce(announcer)
        except Exception as e:
            self.logger.debug("SD announce failed; continuing without: %s", e)

        self.logger.info(
            "SOME/IP Service %#06x:%#06x started on %s:%d",
            self.service_id,
            self.instance_id,
            self.local_addr,
            self.port,
        )

    def stop(self) -> None:
        """Stop the underlying SOME/IP service."""
        if self._service is not None:
            self._service.stop()
            self._service = None
            self.logger.info(
                "SOME/IP Service %#06x:%#06x stopped",
                self.service_id,
                self.instance_id,
            )

    async def notify(self, eventgroup_id: int, event_id: int, payload: bytes) -> None:
        """Notify subscribers of an event."""
        adapter = self._eventgroups.get(eventgroup_id)
        if adapter is None:
            raise ValueError(f"Eventgroup {eventgroup_id:#x} not registered")
        adapter.values[event_id] = payload
        # notify_once is synchronous in pysomeip SimpleEventgroup
        adapter.notify_once([event_id])


class SomeIPPublisher:
    """Event-facing facade over a shared :class:`SomeIPServiceInstance`."""

    def __init__(
        self,
        service_id: int,
        instance_id: int,
        major_version: int,
        local_addr: str,
        port: int,
        instance: Optional[SomeIPServiceInstance] = None,
    ):
        self.service_id = service_id
        self.instance_id = instance_id
        self.major_version = major_version
        self.local_addr = local_addr
        self.port = port
        self.logger = logging.getLogger(__name__)
        self._instance = instance or SomeIPServiceInstance(
            service_id=service_id,
            instance_id=instance_id,
            major_version=major_version,
            local_addr=local_addr,
            port=port,
        )

    @property
    def _service(self) -> Optional[SimpleService]:
        """Compatibility accessor for callers that inspect the pysomeip service."""
        return self._instance.service

    @property
    def service(self) -> Optional[SimpleService]:
        return self._instance.service

    def add_eventgroup(
        self, eventgroup_id: int, on_notification: Callable[[bytes], Awaitable[None]]
    ) -> None:
        self._instance.add_eventgroup(eventgroup_id, on_notification)

    def register_eventgroup(
        self, eventgroup_id: int, on_notification: Callable[[bytes], Awaitable[None]]
    ) -> SomeIPEventgroupAdapter:
        return self._instance.register_eventgroup(eventgroup_id, on_notification)

    def register_method(self, method_id: int, handler: Callable) -> None:
        self._instance.register_method(method_id, handler)

    async def start(self, announcer) -> None:
        await self._instance.start(announcer)

    def stop(self) -> None:
        self._instance.stop()

    async def notify(self, eventgroup_id: int, event_id: int, payload: bytes) -> None:
        await self._instance.notify(eventgroup_id, event_id, payload)


class SomeIPSubscriber:
    """Manages SOME/IP EventGroup subscriptions."""

    def __init__(
        self, local_addr: str, sd_protocol: Optional[ServiceDiscoveryProtocol] = None
    ):
        self.local_addr = local_addr
        self.logger = logging.getLogger(__name__)
        self._sd_prot: Optional[ServiceDiscoveryProtocol] = sd_protocol
        self._handlers: Dict[
            Tuple[int, int, int], Callable[[bytes], Awaitable[None]]
        ] = {}
        # key -> (transport, protocol, eventgroup)
        self._receivers: Dict[
            Tuple[int, int, int],
            Tuple[asyncio.DatagramTransport, SOMEIPDatagramProtocol, Eventgroup],
        ] = {}

    async def start(self) -> None:
        """Initialize Service Discovery."""
        if not self._sd_prot:
            self.logger.warning(
                "ServiceDiscoveryProtocol not provided; subscriptions will not work"
            )
        self.logger.info(
            "Service Discovery initialized on local address %s", self.local_addr
        )

    def stop(self) -> None:
        """Shutdown Service Discovery."""
        # Stop discovery watches and close all receivers
        for key, (trsp, _prot, _evgrp) in list(self._receivers.items()):
            try:
                trsp.close()
            except Exception:
                pass
            self._receivers.pop(key, None)
        self.logger.info("Service Discovery stopped")

    async def subscribe(
        self,
        service_id: int,
        instance_id: int,
        eventgroup_id: int,
        major_version: int,
        on_notification: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Subscribe to a SOME/IP EventGroup."""
        if not self._sd_prot:
            self.logger.error("No ServiceDiscoveryProtocol available; cannot subscribe")
            return

        key = (service_id, instance_id, eventgroup_id)
        self._handlers[key] = on_notification

        # Create a dedicated UDP receiver for this subscription
        class _EventGroupReceiver(SOMEIPDatagramProtocol):
            def message_received(
                self, someip_message: SOMEIPHeader, addr: _T_SOCKNAME, multicast: bool
            ) -> None:
                if someip_message.message_type != SOMEIPMessageType.NOTIFICATION:
                    self.log.warning("unexpected message type: %s", someip_message)
                    return

                async def _dispatch_notification() -> None:
                    await on_notification(someip_message.payload)

                try:
                    asyncio.create_task(_dispatch_notification())
                except Exception as exc:
                    self.log.exception("notification handler failed", exc_info=exc)

        # Create the protocol instance
        prot = _EventGroupReceiver(logger="someip.notification")
        loop = asyncio.get_event_loop()
        # Use create_datagram_endpoint with DatagramProtocolAdapter
        trsp, _ = await loop.create_datagram_endpoint(
            lambda: DatagramProtocolAdapter(prot, is_multicast=False),
            local_addr=(self.local_addr, 0),
        )
        prot.transport = trsp
        sockname = trsp.get_extra_info("sockname")

        # Prepare SD eventgroup subscription
        evgrp = Eventgroup(
            service_id=service_id,
            instance_id=instance_id,
            major_version=major_version,
            eventgroup_id=eventgroup_id,
            sockname=sockname,
            protocol=L4Protocols.UDP,
        )

        # Start SD find+subscribe flow
        self.logger.info(
            f"DEBUG: Initiating SD find_subscribe for Service={service_id:#x}, "
            f"Instance={instance_id:#x}, Eventgroup={eventgroup_id:#x}, Port={sockname[1]}"
        )
        self._sd_prot.discovery.find_subscribe_eventgroup(evgrp)
        self._receivers[key] = (trsp, prot, evgrp)

        self.logger.info(
            f"✓ Subscribed to Service={service_id:#x}, Instance={instance_id:#x}, "
            f"Eventgroup={eventgroup_id:#x} on {sockname}"
        )

    async def unsubscribe(
        self,
        service_id: int,
        instance_id: int,
        eventgroup_id: int,
    ) -> None:
        key = (service_id, instance_id, eventgroup_id)
        if not self._sd_prot:
            return
        trsp, _prot, evgrp = self._receivers.pop(key, (None, None, None))
        if evgrp:
            self._sd_prot.discovery.stop_find_subscribe_eventgroup(evgrp)
        if trsp:
            try:
                trsp.close()
            except Exception:
                pass


class SomeIPEndpoint:
    """Shared SOME/IP participant: SD, transports, publishers, subscriber.

    Event, method, and field adapters can share one endpoint per process so SD
    announcements, unicast ports, and teardown are not duplicated.
    """

    def __init__(
        self,
        local_ip: str = "127.0.0.1",
        publisher_port: int = 30490,
        is_publisher: bool = True,
        mappings: Optional[Iterable[SomeIPTopicMapping]] = None,
    ):
        self.local_ip = local_ip
        self.publisher_port_base = publisher_port
        self.is_publisher = is_publisher
        self.logger = logging.getLogger(__name__)

        self._publishers: Dict[Tuple[int, int], SomeIPPublisher] = {}
        self._services: Dict[Tuple[int, int], SomeIPServiceInstance] = {}
        self._subscriber: Optional[SomeIPSubscriber] = None
        self._sd_prot = None
        self._sd_announcer = None
        self._sd_trsp_u = None
        self._sd_trsp_m = None
        self._started = False

        # Pre-allocate ports for all services known at construction time.
        self._service_ports: Dict[Tuple[int, int], int] = {}
        for mapping in mappings or ():
            service_key = (mapping.service_id, mapping.instance_id)
            if service_key not in self._service_ports:
                port = _get_service_port(
                    mapping.service_id, mapping.instance_id, publisher_port
                )
                self._service_ports[service_key] = port
                self.logger.debug(
                    "Pre-allocated port %d for Service %#x:%#x",
                    port,
                    mapping.service_id,
                    mapping.instance_id,
                )

    @property
    def started(self) -> bool:
        return self._started

    @started.setter
    def started(self, value: bool) -> None:
        self._started = value

    @property
    def subscriber(self) -> Optional[SomeIPSubscriber]:
        return self._subscriber

    @subscriber.setter
    def subscriber(self, value: Optional[SomeIPSubscriber]) -> None:
        self._subscriber = value

    @property
    def publishers(self) -> Dict[Tuple[int, int], SomeIPPublisher]:
        return self._publishers

    @property
    def service_ports(self) -> Dict[Tuple[int, int], int]:
        return self._service_ports

    @property
    def services(self) -> Dict[Tuple[int, int], SomeIPServiceInstance]:
        return self._services

    def get_or_create_service_instance(
        self,
        service_id: int,
        instance_id: int,
        major_version: int,
        *,
        port: Optional[int] = None,
    ) -> SomeIPServiceInstance:
        """Return the shared service instance for a service/instance pair."""
        service_key = (service_id, instance_id)
        instance = self._services.get(service_key)
        if instance is not None:
            return instance
        if port is None:
            port = self._service_ports.get(service_key)
        if port is None:
            port = _get_service_port(service_id, instance_id, self.publisher_port_base)
        self._service_ports[service_key] = port
        instance = SomeIPServiceInstance(
            service_id=service_id,
            instance_id=instance_id,
            major_version=major_version,
            local_addr=self.local_ip,
            port=port,
        )
        self._services[service_key] = instance
        return instance

    @property
    def sd_protocol(self):
        """The SD protocol instance, or ``None`` when SD creation failed."""
        return self._sd_prot

    @property
    def announcer(self):
        """The SD announcer in publisher mode, or ``None``."""
        return self._sd_announcer

    async def start(self) -> None:
        """Initialize SD, transports, and the subscriber-side discovery."""
        if self._started:
            self.logger.warning("SomeIPEndpoint already started")
            return

        mode = "publisher" if self.is_publisher else "subscriber"
        self.logger.info(
            "Starting SomeIPEndpoint on %s (ports starting from %d) [%s mode]",
            self.local_ip,
            self.publisher_port_base,
            mode,
        )

        try:
            sd_trsp_u, sd_trsp_m, sd_prot = (
                await ServiceDiscoveryProtocol.create_endpoints(
                    family=socket.AF_INET,
                    local_addr=self.local_ip,
                    multicast_addr="224.224.224.245",
                )
            )
            self._sd_prot = sd_prot
            self._sd_trsp_u = sd_trsp_u
            self._sd_trsp_m = sd_trsp_m
            sd_prot.start()

            if self.is_publisher:
                self._sd_announcer = sd_prot.announcer
                self.logger.info(
                    "Service Discovery initialized (publisher mode with announcer)"
                )
            else:
                self._sd_announcer = None
                self.logger.info(
                    "Service Discovery initialized (subscriber mode, discovery only)"
                )
        except OSError as e:
            # Another process may already own SD port 30490; subscriptions can
            # still work through the shared multicast group.
            self.logger.info("SD creation failed (expected in multi-process): %s", e)
            self._sd_announcer = None
            self._sd_prot = None
            self._sd_trsp_u = None
            self._sd_trsp_m = None

        self._subscriber = SomeIPSubscriber(self.local_ip, sd_protocol=self._sd_prot)
        await self._subscriber.start()
        self._started = True
        self.logger.info("SomeIPEndpoint started successfully")

    async def stop(self) -> None:
        """Stop publishers, the subscriber, and SD transports."""
        if not self._started:
            return

        self.logger.info("Stopping SomeIPEndpoint...")
        for instance in self._services.values():
            instance.stop()
        self._services.clear()
        self._publishers.clear()

        if self._subscriber:
            self._subscriber.stop()
            self._subscriber = None

        if self._sd_prot:
            try:
                self._sd_prot.stop()
            except Exception:
                pass
        for trsp_name in ("_sd_trsp_u", "_sd_trsp_m"):
            trsp = getattr(self, trsp_name, None)
            if trsp:
                try:
                    trsp.close()
                except Exception:
                    pass
                setattr(self, trsp_name, None)

        self._started = False
        self.logger.info("SomeIPEndpoint stopped")

    async def get_or_create_publisher(
        self,
        service_id: int,
        instance_id: int,
        major_version: int,
        eventgroup_id: int,
        on_notification: Callable[[bytes], Awaitable[None]],
    ) -> SomeIPPublisher:
        """Return the service publisher, creating and announcing it once."""
        service_key = (service_id, instance_id)
        instance = self.get_or_create_service_instance(
            service_id, instance_id, major_version
        )
        publisher = self._publishers.get(service_key)
        if publisher is None:
            publisher = SomeIPPublisher(
                service_id=service_id,
                instance_id=instance_id,
                major_version=major_version,
                local_addr=self.local_ip,
                port=instance.port,
                instance=instance,
            )
            self._publishers[service_key] = publisher
        publisher.add_eventgroup(eventgroup_id, on_notification)
        await publisher.start(self._sd_announcer)
        return publisher

    async def subscribe(
        self,
        service_id: int,
        instance_id: int,
        eventgroup_id: int,
        major_version: int,
        on_notification: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Subscribe to a remote eventgroup through SD."""
        if self._subscriber is None:
            raise RuntimeError("SomeIPEndpoint is not started")
        await self._subscriber.subscribe(
            service_id=service_id,
            instance_id=instance_id,
            eventgroup_id=eventgroup_id,
            major_version=major_version,
            on_notification=on_notification,
        )

    async def unsubscribe(
        self, service_id: int, instance_id: int, eventgroup_id: int
    ) -> None:
        """Stop a remote eventgroup subscription."""
        if self._subscriber is not None:
            await self._subscriber.unsubscribe(
                service_id=service_id,
                instance_id=instance_id,
                eventgroup_id=eventgroup_id,
            )


class SomeIPEventBus(ManagedEventBus):
    """
    EventBus implementation over SOME/IP.

    Topology ``PEER``: publishers and subscribers talk directly; endpoints find
    each other through SOME/IP Service Discovery (no central broker).  The same
    topology models DDS (RTPS discovery) for a future implementation.

    Dual-mode operation:
    - Publisher: Provides SOME/IP services with EventGroups.
    - Subscriber: Discovers and subscribes to remote SOME/IP EventGroups.

    Topics map to (service_id, instance_id, eventgroup_id) tuples.
    """

    topology = Topology.PEER

    def __init__(
        self,
        mappings: Dict[str, SomeIPTopicMapping],
        local_ip: str = "127.0.0.1",
        publisher_port: int = 30490,
        is_publisher: bool = True,
        *,
        endpoint: Optional[SomeIPEndpoint] = None,
    ):
        super().__init__()
        self.mappings = mappings
        self.logger = logging.getLogger(__name__)

        # Local subscriptions (topic -> list of handlers)
        self._subscriptions: Dict[str, List[Subscription]] = {}

        # Background SD subscription tasks; kept referenced so they are never
        # garbage-collected mid-flight and can be cancelled on stop().
        self._background_tasks: Set[asyncio.Task[None]] = set()

        # SD, transports, publishers and subscriber can be shared with method
        # and field adapters through one endpoint.
        self._owns_endpoint = endpoint is None
        self._endpoint = endpoint or SomeIPEndpoint(
            local_ip=local_ip,
            publisher_port=publisher_port,
            is_publisher=is_publisher,
            mappings=mappings.values(),
        )

    # Compatibility accessors for callers/tests that used the old internals.
    @property
    def local_ip(self) -> str:
        return self._endpoint.local_ip

    @property
    def publisher_port_base(self) -> int:
        return self._endpoint.publisher_port_base

    @property
    def is_publisher(self) -> bool:
        return self._endpoint.is_publisher

    @property
    def _started(self) -> bool:
        return self._endpoint.started

    @_started.setter
    def _started(self, value: bool) -> None:
        self._endpoint.started = value

    @property
    def _publishers(self) -> Dict[Tuple[int, int], SomeIPPublisher]:
        return self._endpoint.publishers

    @property
    def _service_ports(self) -> Dict[Tuple[int, int], int]:
        return self._endpoint.service_ports

    @property
    def _subscriber(self) -> Optional[SomeIPSubscriber]:
        return self._endpoint.subscriber

    @_subscriber.setter
    def _subscriber(self, value: Optional[SomeIPSubscriber]) -> None:
        self._endpoint.subscriber = value

    def _spawn_task(self, coro: Coroutine[object, object, None]) -> None:
        """Run a background SD task and keep a strong reference to it."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _cancel_background_tasks(self) -> None:
        """Cancel and drain in-flight SD subscription tasks."""
        tasks = list(self._background_tasks)
        self._background_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start(self):
        """Initialize the shared SOME/IP endpoint (SD + transports)."""
        if self._endpoint.started:
            return
        self.logger.info("Starting SomeIPEventBus ...")
        await self._endpoint.start()
        self.logger.info("SomeIPEventBus started successfully")

    async def stop(self):
        """Cancel SD tasks and shut down the endpoint when this bus owns it."""
        await self._cancel_background_tasks()
        if self._owns_endpoint and self._endpoint.started:
            self.logger.info("Stopping SomeIPEventBus...")
            await self._endpoint.stop()
            self.logger.info("SomeIPEventBus stopped")
        self._clear_registrations()

    async def publish(self, message: EventMessage) -> None:
        """
        Publish a message to a SOME/IP EventGroup.

        Steps:
        1. Resolve topic to mapping.
        2. Ensure we are providing this Service.
        3. Serialize message.
        4. Notify subscribers.
        """
        mapping = self.mappings.get(message.topic)
        if not mapping:
            self.logger.warning(f"No SOME/IP mapping for topic: {message.topic}")
            return

        if not self._started:
            self.logger.warning("SomeIPEventBus not started")
            return

        payload = self._serialize_message(message)

        publisher = await self._endpoint.get_or_create_publisher(
            service_id=mapping.service_id,
            instance_id=mapping.instance_id,
            major_version=mapping.major_version,
            eventgroup_id=mapping.eventgroup_id,
            on_notification=self._create_notification_handler(message.topic),
        )
        await publisher.notify(mapping.eventgroup_id, mapping.event_id, payload)

        self.logger.debug(
            f"Published to Service={mapping.service_id:#x}, "
            f"Instance={mapping.instance_id:#x}, Group={mapping.eventgroup_id:#x}"
        )

    async def register_topic(self, topic: str) -> None:
        """Create and announce the publisher for a topic without publishing."""
        mapping = self.mappings.get(topic)
        if not mapping:
            raise NotFoundError(f"No SOME/IP mapping for topic: {topic}")
        if not self._started:
            raise StateError("SomeIPEventBus is not started")
        await self._endpoint.get_or_create_publisher(
            service_id=mapping.service_id,
            instance_id=mapping.instance_id,
            major_version=mapping.major_version,
            eventgroup_id=mapping.eventgroup_id,
            on_notification=self._create_notification_handler(topic),
        )

    async def _on_publisher_registered(self, topic: str) -> None:
        """SOME/IP publisher registration is an SD Offer/announce."""
        await self.register_topic(topic)

    async def _on_publisher_unregistered(self, topic: str) -> None:
        """Release the local publish gate.

        pysomeip has no per-eventgroup StopOffer, so the SD offer remains until
        the endpoint stops; the bus still refuses to publish this topic once
        its last publisher registration is gone.
        """
        self.logger.info(
            "Publisher registration released for topic %s; SD offer remains "
            "until endpoint stop",
            topic,
        )

    def subscribe(self, topic: str, handler: EventHandler) -> Subscription:
        """
        Subscribe to a SOME/IP EventGroup.

        Steps:
        1. Resolve topic to mapping.
        2. If first subscription, start SD search.
        3. Register local handler.
        """
        mapping = self.mappings.get(topic)
        if not mapping:
            raise ValueError(f"No SOME/IP mapping for topic: {topic}")

        if not self._started:
            raise RuntimeError("SomeIPEventBus not started")

        sub = Subscription.new(topic, handler)

        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
            # Get and record subscription sequence number NOW (in subscribe call order)
            global _SUBSCRIPTION_COUNTER, _SUBSCRIPTION_LOCK
            with _SUBSCRIPTION_LOCK:
                seq_num = _SUBSCRIPTION_COUNTER
                _SUBSCRIPTION_COUNTER += 1

            # Initiate SOME/IP subscription with deterministic sequence-based delay
            self.logger.info(
                f"[Sub #{seq_num}] Starting SOME/IP subscription for topic: {topic}"
            )
            self._spawn_task(self._start_subscription(mapping, topic, seq_num))

        self._subscriptions[topic].append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        """Unsubscribe from a topic."""
        if subscription.topic in self._subscriptions:
            self._subscriptions[subscription.topic].remove(subscription)
            if not self._subscriptions[subscription.topic]:
                del self._subscriptions[subscription.topic]
                # Stop SOME/IP subscription
                mapping = self.mappings.get(subscription.topic)
                if mapping and self._subscriber:
                    self._spawn_task(self._stop_subscription(mapping))

    def get_subscribers_count(self, topic: str) -> int:
        """Return the number of local subscribers for a topic."""
        return len(self._subscriptions.get(topic, []))

    async def _start_subscription(
        self, mapping: SomeIPTopicMapping, topic: str, seq_num: int
    ) -> None:
        """Initiate SOME/IP subscription through Service Discovery."""
        try:
            # Calculate delay: Wait long enough for ALL publishers to start and announce
            # Base delay of 5 seconds ensures all publishers are ready
            # Then add per-subscription delay to stagger requests
            delay = 5.0 + (seq_num * 0.8)

            self.logger.info(
                f"[Sub #{seq_num}] Waiting {delay:.2f}s before SD find_subscribe for {topic}"
            )
            await asyncio.sleep(delay)

            self.logger.info(
                f"[Sub #{seq_num}] Initiating SD find_subscribe for {topic}: "
                f"Service=0x{mapping.service_id:04x}, Instance=0x{mapping.instance_id:04x}"
            )

            async def on_notification(payload: bytes):
                """Deserialize and dispatch notification to all local handlers."""
                try:
                    message = self._deserialize_message(payload)
                    subs = list(self._subscriptions.get(topic, []))
                    for sub in subs:
                        try:
                            await sub.handler(message)
                        except Exception as e:
                            self.logger.error(f"Handler error for {topic}: {e}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to deserialize notification for {topic}: {e}"
                    )

            await self._endpoint.subscribe(
                service_id=mapping.service_id,
                instance_id=mapping.instance_id,
                eventgroup_id=mapping.eventgroup_id,
                major_version=mapping.major_version,
                on_notification=on_notification,
            )

            self.logger.info(
                f"✓ [Sub #{seq_num}] Successfully initiated subscription for {topic}"
            )

        except Exception as e:
            self.logger.error(f"Failed to subscribe to {topic}: {e}", exc_info=True)

    async def _stop_subscription(self, mapping: SomeIPTopicMapping) -> None:
        """Stop SOME/IP subscription through Service Discovery."""
        await self._endpoint.unsubscribe(
            service_id=mapping.service_id,
            instance_id=mapping.instance_id,
            eventgroup_id=mapping.eventgroup_id,
        )

    def _serialize_message(self, message: EventMessage) -> bytes:
        """Convert EventMessage to bytes for SOME/IP payload."""
        data_dict = message.to_dict()
        json_str = json.dumps(data_dict)
        return json_str.encode("utf-8")

    def _deserialize_message(self, payload: bytes) -> EventMessage:
        """Convert SOME/IP payload bytes back to EventMessage."""
        json_str = payload.decode("utf-8")
        data_dict = json.loads(json_str)
        return EventMessage.from_dict(data_dict)

    def _create_notification_handler(self, topic: str):
        """Create a handler for incoming notifications."""

        async def handler(payload: bytes):
            self.logger.debug(f"Notification received for {topic}")

        return handler
