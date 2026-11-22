"""Config-driven wiring for the SOME/IP pub/sub echo example."""

from __future__ import annotations

from examples.someip_pubsub_echo._common import (
    SERVICE_ID,
    TOPIC,
    publisher_config,
    subscriber_config,
)
from tinysoa.config import create_event_bus
from tinysoa.eventbus import SomeIPEventBus


def test_publisher_config_builds_a_someip_bus() -> None:
    bus = create_event_bus(publisher_config())
    assert isinstance(bus, SomeIPEventBus)
    assert bus.is_publisher is True
    assert bus.mappings[TOPIC].service_id == SERVICE_ID


def test_subscriber_config_builds_a_discovery_bus() -> None:
    bus = create_event_bus(subscriber_config())
    assert isinstance(bus, SomeIPEventBus)
    assert bus.is_publisher is False
    assert bus.mappings[TOPIC].service_id == SERVICE_ID
