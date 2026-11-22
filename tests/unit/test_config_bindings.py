"""Tests for protocol-agnostic EventBus config and factory."""

from __future__ import annotations

import pytest

from tinysoa.config import (
    EventBusConfig,
    EventBusKind,
    TopicBinding,
    create_event_bus,
)
from tinysoa.core.errors import ValidationError
from tinysoa.eventbus import InMemoryEventBus, SomeIPEventBus, TCPEventBus


def test_topic_binding_rejects_empty_topic() -> None:
    with pytest.raises(ValidationError):
        TopicBinding("")


def test_event_bus_config_rejects_duplicate_topics() -> None:
    with pytest.raises(ValidationError):
        EventBusConfig(
            kind=EventBusKind.INMEMORY,
            bindings=(TopicBinding("a"), TopicBinding("a")),
        )


def test_event_bus_config_coerces_kind_string() -> None:
    config = EventBusConfig(kind="tcp")  # type: ignore[arg-type]
    assert config.kind is EventBusKind.TCP


def test_event_bus_config_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        EventBusConfig(kind="bogus")  # type: ignore[arg-type]


def test_inmemory_config_creates_inmemory_bus() -> None:
    bus = create_event_bus(EventBusConfig(kind=EventBusKind.INMEMORY))
    assert isinstance(bus, InMemoryEventBus)


def test_tcp_config_creates_tcp_bus() -> None:
    bus = create_event_bus(
        EventBusConfig(
            kind=EventBusKind.TCP,
            options={"host": "127.0.0.1", "port": 19001},
        )
    )
    assert isinstance(bus, TCPEventBus)
    assert bus.host == "127.0.0.1"
    assert bus.port == 19001


def test_someip_config_builds_mapping_table() -> None:
    config = EventBusConfig(
        kind=EventBusKind.SOMEIP,
        service="temperature",
        bindings=(
            TopicBinding(
                "sensor.temperature",
                {
                    "service_id": 0x1001,
                    "instance_id": 0x0001,
                    "eventgroup_id": 0x0001,
                    "event_id": 0x0002,
                    "major_version": 1,
                },
            ),
        ),
        options={"local_ip": "127.0.0.1", "publisher_port": 31000},
    )
    bus = create_event_bus(config)
    assert isinstance(bus, SomeIPEventBus)
    mapping = bus.mappings["sensor.temperature"]
    assert mapping.service_id == 0x1001
    assert mapping.instance_id == 0x0001
    assert mapping.eventgroup_id == 0x0001
    assert mapping.event_id == 0x0002


def test_someip_config_requires_at_least_one_binding() -> None:
    with pytest.raises(ValidationError):
        create_event_bus(EventBusConfig(kind=EventBusKind.SOMEIP))


def test_someip_config_requires_service_id() -> None:
    config = EventBusConfig(
        kind=EventBusKind.SOMEIP,
        bindings=(TopicBinding("t", {"instance_id": 1, "eventgroup_id": 1}),),
    )
    with pytest.raises(ValidationError, match="service_id"):
        create_event_bus(config)


def test_someip_config_rejects_out_of_range_id() -> None:
    config = EventBusConfig(
        kind=EventBusKind.SOMEIP,
        bindings=(
            TopicBinding(
                "t",
                {"service_id": 0x10000, "instance_id": 1, "eventgroup_id": 1},
            ),
        ),
    )
    with pytest.raises(ValidationError, match="service_id"):
        create_event_bus(config)


def test_someip_config_rejects_invalid_l4_protocol() -> None:
    config = EventBusConfig(
        kind=EventBusKind.SOMEIP,
        bindings=(
            TopicBinding(
                "t",
                {
                    "service_id": 1,
                    "instance_id": 1,
                    "eventgroup_id": 1,
                    "l4_protocol": "SCTP",
                },
            ),
        ),
    )
    with pytest.raises(ValidationError, match="l4_protocol"):
        create_event_bus(config)
