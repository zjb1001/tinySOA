"""Config wiring for the SOME/IP one-to-one example."""

from __future__ import annotations

from examples.someip_pubsub_one_to_one._common import (
    EVENT_MAPPINGS,
    SERVICE_ID,
    TOPIC,
    service_binding,
)
from examples.someip_pubsub_one_to_one.publisher import (
    parse_args as parse_publisher_args,
)
from examples.someip_pubsub_one_to_one.subscriber import (
    parse_args as parse_subscriber_args,
)
from tinysoa.eventbus import SomeIPService, TopicPublisher, TopicSubscriber


def test_publisher_service_exposes_topic_views() -> None:
    service = SomeIPService(
        service_binding(server_port=30970),
        event_mappings=EVENT_MAPPINGS,
        is_publisher=True,
    )
    assert isinstance(service.publisher(TOPIC), TopicPublisher)
    assert service.event_bus is not None
    assert service.event_bus.mappings[TOPIC].service_id == SERVICE_ID


def test_subscriber_service_exposes_topic_views() -> None:
    service = SomeIPService(
        service_binding(local_port=30981),
        event_mappings=EVENT_MAPPINGS,
        is_publisher=False,
    )
    assert isinstance(service.subscriber(TOPIC), TopicSubscriber)
    assert service.event_bus is not None
    assert service.event_bus.mappings[TOPIC].service_id == SERVICE_ID


def test_publisher_cli_defaults() -> None:
    args = parse_publisher_args([])
    assert args.count == 20
    assert args.interval == 1.0


def test_subscriber_cli_defaults() -> None:
    args = parse_subscriber_args([])
    assert args.want == 3
    assert args.local_port == 30980
