from __future__ import annotations

import asyncio
import json
import logging
import socket
import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any, List, Callable, Awaitable
from uuid import uuid4
from threading import Lock

from tinysoa.eventbus.bus import EventBus, Subscription, EventHandler
from tinysoa.eventbus.message import EventMessage

# Import pysomeip components
from someip.service import SimpleService, SimpleEventgroup
from someip.sd import ServiceDiscoveryProtocol, EventgroupSubscription, SOMEIPDatagramProtocol, DatagramProtocolAdapter
from someip.header import SOMEIPHeader, _T_SOCKNAME, SOMEIPMessageType, L4Protocols
from someip.config import Eventgroup


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
        interval: Optional[float] = 0.5
    ):
        super().__init__(service, id=eventgroup_id, interval=interval)
        self.on_notification = on_notification

    async def handle_notification(self, payload: bytes) -> None:
        """Called when a notification is received."""
        await self.on_notification(payload)


class SomeIPPublisher:
    """Manages SOME/IP service publication."""

    def __init__(
        self,
        service_id: int,
        instance_id: int,
        major_version: int,
        local_addr: str,
        port: int
    ):
        self.service_id = service_id
        self.instance_id = instance_id
        self.major_version = major_version
        self.local_addr = local_addr
        self.port = port
        self.logger = logging.getLogger(__name__)
        self._service: Optional[SimpleService] = None
        self._eventgroups: Dict[int, SomeIPEventgroupAdapter] = {}
        self._pending_eventgroups: List[Tuple[int, Callable[[bytes], Awaitable[None]]]] = []

    def add_eventgroup(self, eventgroup_id: int, on_notification: Callable[[bytes], Awaitable[None]]) -> None:
        """Queue/register an eventgroup; if not started, register later before SD announce."""
        if self._service is not None:
            if eventgroup_id not in self._eventgroups:
                adapter = SomeIPEventgroupAdapter(self._service, eventgroup_id, on_notification, interval=0.5)
                self._service.register_eventgroup(adapter)
                self._eventgroups[eventgroup_id] = adapter
            return
        self._pending_eventgroups.append((eventgroup_id, on_notification))

    async def start(self, announcer) -> None:
        """Start SOME/IP service and announce after registering eventgroups."""
        # Dynamically create a service class
        ServiceClass = type(
            f'Service_{self.service_id:04x}_{self.instance_id:04x}',
            (SimpleService,),
            {
                'service_id': self.service_id,
                'version_major': self.major_version,
                'version_minor': 0,
            }
        )

        # Bind UDP endpoint without announcing so we can register eventgroups first
        try:
            _trsp, prot = await ServiceClass.create_unicast_endpoint(
                instance_id=self.instance_id,
                local_addr=(self.local_addr, self.port)
            )
            self._service = prot
        except OSError as e:
            self.logger.error(f"Failed to bind service to {self.local_addr}:{self.port}: {e}")
            raise

        # Register pending eventgroups before announce so SD matches subscriptions
        for eg_id, cb in self._pending_eventgroups:
            adapter = SomeIPEventgroupAdapter(self._service, eg_id, cb, interval=0.5)
            self._service.register_eventgroup(adapter)
            self._eventgroups[eg_id] = adapter
        self._pending_eventgroups.clear()

        # Now announce (if SD announcer is available)
        try:
            if announcer is not None:
                self._service.start_announce(announcer)
        except Exception as e:
            self.logger.debug(f"SD announce failed; continuing without: {e}")

        self.logger.info(
            f"SOME/IP Service {self.service_id:#x}:{self.instance_id:#x} started on "
            f"{self.local_addr}:{self.port}"
        )

    def stop(self) -> None:
        """Stop SOME/IP service."""
        if self._service:
            self._service.stop()
            self.logger.info(
                f"SOME/IP Service {self.service_id:#x}:{self.instance_id:#x} stopped"
            )

    def register_eventgroup(
        self, 
        eventgroup_id: int,
        on_notification: Callable[[bytes], Awaitable[None]]
    ) -> SomeIPEventgroupAdapter:
        """Register an eventgroup for publishing."""
        if not self._service:
            raise RuntimeError("Service not started")
        
        adapter = SomeIPEventgroupAdapter(
            self._service,
            eventgroup_id,
            on_notification
        )
        self._service.register_eventgroup(adapter)
        self._eventgroups[eventgroup_id] = adapter
        
        self.logger.debug(
            f"Registered eventgroup {eventgroup_id:#x} on service "
            f"{self.service_id:#x}:{self.instance_id:#x}"
        )
        return adapter

    async def notify(self, eventgroup_id: int, event_id: int, payload: bytes) -> None:
        """Notify subscribers of an event."""
        if eventgroup_id not in self._eventgroups:
            raise ValueError(f"Eventgroup {eventgroup_id:#x} not registered")

        adapter = self._eventgroups[eventgroup_id]
        adapter.values[event_id] = payload
        # notify_once is synchronous in pysomeip SimpleEventgroup
        adapter.notify_once([event_id])


class SomeIPSubscriber:
    """Manages SOME/IP EventGroup subscriptions."""

    def __init__(self, local_addr: str, sd_protocol: Optional[ServiceDiscoveryProtocol] = None):
        self.local_addr = local_addr
        self.logger = logging.getLogger(__name__)
        self._sd_prot: Optional[ServiceDiscoveryProtocol] = sd_protocol
        self._handlers: Dict[Tuple[int, int, int], Callable[[bytes], Awaitable[None]]] = {}
        # key -> (transport, protocol, eventgroup)
        self._receivers: Dict[
            Tuple[int, int, int],
            Tuple[asyncio.DatagramTransport, SOMEIPDatagramProtocol, Eventgroup],
        ] = {}

    async def start(self) -> None:
        """Initialize Service Discovery."""
        if not self._sd_prot:
            self.logger.warning("ServiceDiscoveryProtocol not provided; subscriptions will not work")
        self.logger.info("Service Discovery initialized on local address %s", self.local_addr)

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
        on_notification: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """Subscribe to a SOME/IP EventGroup."""
        if not self._sd_prot:
            self.logger.error("No ServiceDiscoveryProtocol available; cannot subscribe")
            return

        key = (service_id, instance_id, eventgroup_id)
        self._handlers[key] = on_notification

        # Create a dedicated UDP receiver for this subscription
        class _EventGroupReceiver(SOMEIPDatagramProtocol):
            def message_received(self, someip_message: SOMEIPHeader, addr: _T_SOCKNAME, multicast: bool) -> None:
                if someip_message.message_type != SOMEIPMessageType.NOTIFICATION:
                    self.log.warning("unexpected message type: %s", someip_message)
                    return
                try:
                    asyncio.create_task(on_notification(someip_message.payload))
                except Exception as exc:
                    self.log.exception("notification handler failed", exc_info=exc)

        # Create the protocol instance
        prot = _EventGroupReceiver(logger="someip.notification")
        loop = asyncio.get_event_loop()
        # Use create_datagram_endpoint with DatagramProtocolAdapter
        trsp, _ = await loop.create_datagram_endpoint(
            lambda: DatagramProtocolAdapter(prot, is_multicast=False),
            local_addr=(self.local_addr, 0)
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


class SomeIPEventBus(EventBus):
    """
    EventBus implementation over SOME/IP.
    
    Dual-mode operation:
    - Publisher: Provides SOME/IP services with EventGroups.
    - Subscriber: Discovers and subscribes to remote SOME/IP EventGroups.
    
    Topics map to (service_id, instance_id, eventgroup_id) tuples.
    """

    def __init__(
        self,
        mappings: Dict[str, SomeIPTopicMapping],
        local_ip: str = "127.0.0.1",
        publisher_port: int = 30490,
        is_publisher: bool = True
    ):
        self.mappings = mappings
        self.local_ip = local_ip
        self.publisher_port_base = publisher_port
        self.is_publisher = is_publisher
        self.logger = logging.getLogger(__name__)
        
        # Local subscriptions (topic -> list of handlers)
        self._subscriptions: Dict[str, List[Subscription]] = {}
        
        # SOME/IP Protocol stack
        self._publishers: Dict[Tuple[int, int], SomeIPPublisher] = {}  # (service_id, instance_id)
        self._subscriber: Optional[SomeIPSubscriber] = None
        self._sd_announcer = None
        self._started = False
        
        # Pre-allocate ports for all services in this EventBus
        self._service_ports: Dict[Tuple[int, int], int] = {}
        for topic, mapping in mappings.items():
            service_key = (mapping.service_id, mapping.instance_id)
            if service_key not in self._service_ports:
                port = _get_service_port(mapping.service_id, mapping.instance_id, publisher_port)
                self._service_ports[service_key] = port
                self.logger.debug(
                    f"Pre-allocated port {port} for Service {mapping.service_id:#x}:"
                    f"{mapping.instance_id:#x}"
                )

    async def start(self):
        """Initialize SOME/IP protocol stack (SD + endpoints)."""
        if self._started:
            self.logger.warning("SomeIPEventBus already started")
            return
        
        mode = "publisher" if self.is_publisher else "subscriber"
        self.logger.info(f"Starting SomeIPEventBus on {self.local_ip} (ports starting from {self.publisher_port_base}) [{mode} mode]")
        
        # Initialize Service Discovery
        try:
            sd_trsp_u, sd_trsp_m, sd_prot = await ServiceDiscoveryProtocol.create_endpoints(
                family=socket.AF_INET,
                local_addr=self.local_ip,
                multicast_addr="224.224.224.245"
            )
            
            self._sd_prot = sd_prot
            self._sd_trsp_u = sd_trsp_u
            self._sd_trsp_m = sd_trsp_m
            sd_prot.start()
            
            if self.is_publisher:
                # Publisher: set announcer for advertising services
                self._sd_announcer = sd_prot.announcer
                self.logger.info("Service Discovery initialized (publisher mode with announcer)")
            else:
                # Subscriber: disable announcer, only use discovery
                self._sd_announcer = None
                self.logger.info("Service Discovery initialized (subscriber mode, discovery only)")
                
        except OSError as e:
            # In multi-process scenarios where another process already created SD on this port
            # (e.g., port 30490 busy), we still allow subscription through shared multicast
            self.logger.info(f"SD creation failed (expected in multi-process): {e}")
            self._sd_announcer = None
            self._sd_prot = None
            self._sd_trsp_u = None
            self._sd_trsp_m = None
        
        # Initialize subscriber (for remote service discovery)
        self._subscriber = SomeIPSubscriber(self.local_ip, sd_protocol=self._sd_prot)
        await self._subscriber.start()
        
        self._started = True
        self.logger.info("SomeIPEventBus started successfully")

    async def stop(self):
        """Shutdown SOME/IP stack."""
        if not self._started:
            return
        
        self.logger.info("Stopping SomeIPEventBus...")
        
        # Stop all publishers
        for publisher in self._publishers.values():
            publisher.stop()
        self._publishers.clear()
        
        # Stop subscriber
        if self._subscriber:
            self._subscriber.stop()
            self._subscriber = None

        # Stop SD and close transports if we created them
        if getattr(self, "_sd_prot", None):
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
        self.logger.info("SomeIPEventBus stopped")

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
        
        # Get or create publisher for this service
        service_key = (mapping.service_id, mapping.instance_id)
        if service_key not in self._publishers:
            # Use pre-allocated port for this service
            publisher_port = self._service_ports.get(service_key, _get_service_port(
                mapping.service_id, mapping.instance_id, self.publisher_port_base
            ))
            
            publisher = SomeIPPublisher(
                service_id=mapping.service_id,
                instance_id=mapping.instance_id,
                major_version=mapping.major_version,
                local_addr=self.local_ip,
                port=publisher_port
            )
            publisher.add_eventgroup(
                mapping.eventgroup_id,
                self._create_notification_handler(message.topic)
            )
            await publisher.start(self._sd_announcer)
            self._publishers[service_key] = publisher
        
        publisher = self._publishers[service_key]
        await publisher.notify(mapping.eventgroup_id, mapping.event_id, payload)
        
        self.logger.debug(
            f"Published to Service={mapping.service_id:#x}, "
            f"Instance={mapping.instance_id:#x}, Group={mapping.eventgroup_id:#x}"
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
            self.logger.info(f"[Sub #{seq_num}] Starting SOME/IP subscription for topic: {topic}")
            asyncio.create_task(self._start_subscription(mapping, topic, seq_num))
            
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
                    asyncio.create_task(self._stop_subscription(mapping))

    def get_subscribers_count(self, topic: str) -> int:
        """Return the number of local subscribers for a topic."""
        return len(self._subscriptions.get(topic, []))

    async def _start_subscription(self, mapping: SomeIPTopicMapping, topic: str, seq_num: int) -> None:
        """Initiate SOME/IP subscription through Service Discovery."""
        if not self._subscriber:
            self.logger.error("Subscriber not initialized")
            return

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
                    self.logger.error(f"Failed to deserialize notification for {topic}: {e}")

            await self._subscriber.subscribe(
                service_id=mapping.service_id,
                instance_id=mapping.instance_id,
                eventgroup_id=mapping.eventgroup_id,
                major_version=mapping.major_version,
                on_notification=on_notification
            )
            
            self.logger.info(f"✓ [Sub #{seq_num}] Successfully initiated subscription for {topic}")
            
        except Exception as e:
            self.logger.error(f"Failed to subscribe to {topic}: {e}", exc_info=True)

    async def _stop_subscription(self, mapping: SomeIPTopicMapping) -> None:
        """Stop SOME/IP subscription through Service Discovery."""
        if self._subscriber:
            await self._subscriber.unsubscribe(
                service_id=mapping.service_id,
                instance_id=mapping.instance_id,
                eventgroup_id=mapping.eventgroup_id
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
