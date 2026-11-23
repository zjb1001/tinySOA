from __future__ import annotations

from typing import Dict

from tinysoa.core.errors import ValidationError
from tinysoa.eventbus.bus import ManagedEventBus
from tinysoa.eventbus.memory import InMemoryEventBus
from tinysoa.eventbus.tcp import TCPEventBus

from .bindings import EventBusConfig, EventBusKind

_SOMEIP_MAX_ID = 0xFFFF


def create_event_bus(config: EventBusConfig) -> ManagedEventBus:
    """Build a managed event bus from a protocol-agnostic configuration.

    The application only supplies topics and endpoint options; the factory
    translates them into the concrete transport.  Call ``await bus.start()``
    for TCP and SOME/IP buses.
    """
    if config.kind is EventBusKind.INMEMORY:
        return InMemoryEventBus()
    if config.kind is EventBusKind.TCP:
        return TCPEventBus(
            host=config.option_str("host", "127.0.0.1"),
            port=config.option_int("port", 8765, minimum=1, maximum=65535),
        )
    if config.kind is EventBusKind.SOMEIP:
        return _create_someip_bus(config)
    raise ValidationError(f"Unsupported EventBusKind: {config.kind!r}")


def _create_someip_bus(config: EventBusConfig) -> ManagedEventBus:
    # Lazy import keeps InMemory/TCP users independent of pysomeip.
    from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping

    if not config.bindings:
        raise ValidationError(
            "SOME/IP EventBusConfig requires at least one TopicBinding"
        )

    mappings: Dict[str, SomeIPTopicMapping] = {}
    for binding in config.bindings:
        l4_protocol = binding.require_str("l4_protocol", default="UDP").upper()
        if l4_protocol not in ("UDP", "TCP"):
            raise ValidationError(
                f"TopicBinding[{binding.topic}].l4_protocol must be UDP or TCP"
            )
        mappings[binding.topic] = SomeIPTopicMapping(
            service_id=binding.require_int(
                "service_id", minimum=0, maximum=_SOMEIP_MAX_ID
            ),
            instance_id=binding.require_int(
                "instance_id", minimum=0, maximum=_SOMEIP_MAX_ID
            ),
            eventgroup_id=binding.require_int(
                "eventgroup_id", minimum=0, maximum=_SOMEIP_MAX_ID
            ),
            major_version=binding.require_int(
                "major_version", default=1, minimum=0, maximum=0xFF
            ),
            minor_version=binding.require_int(
                "minor_version", default=0, minimum=0, maximum=0xFFFFFFFF
            ),
            event_id=binding.require_int(
                "event_id", default=0x0001, minimum=0, maximum=_SOMEIP_MAX_ID
            ),
            l4_protocol=l4_protocol,
        )

    return SomeIPEventBus(
        mappings,
        local_ip=config.option_str("local_ip", "127.0.0.1"),
        publisher_port=config.option_int(
            "publisher_port", 30490, minimum=1, maximum=65535
        ),
        is_publisher=config.option_bool("is_publisher", True),
    )
