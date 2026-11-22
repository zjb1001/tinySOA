"""Config wiring for the SOME/IP one-to-many example."""

from __future__ import annotations

from examples.someip_pubsub_one_to_many._common import (
    SERVICE_ID,
    TOPIC,
    publisher_config,
    subscriber_config,
)
from examples.someip_pubsub_one_to_many.publisher import (
    parse_args as parse_publisher_args,
)
from examples.someip_pubsub_one_to_many.subscriber import (
    parse_args as parse_subscriber_args,
)
from tinysoa.config import create_event_bus
from tinysoa.eventbus import SomeIPEventBus


def test_publisher_config_builds_someip_bus() -> None:
    bus = create_event_bus(publisher_config())
    assert isinstance(bus, SomeIPEventBus)
    assert bus.is_publisher is True
    assert bus.mappings[TOPIC].service_id == SERVICE_ID


def test_subscriber_config_builds_discovery_bus() -> None:
    bus = create_event_bus(subscriber_config(30931))
    assert isinstance(bus, SomeIPEventBus)
    assert bus.is_publisher is False
    assert bus.mappings[TOPIC].service_id == SERVICE_ID
    assert bus.publisher_port_base == 30931


def test_publisher_cli_defaults() -> None:
    args = parse_publisher_args([])
    assert args.count == 20
    assert args.interval == 1.0


def test_subscriber_cli_defaults() -> None:
    args = parse_subscriber_args(["sub-1"])
    assert args.subscriber_id == "sub-1"
    assert args.want == 3
    assert args.local_port == 30930
