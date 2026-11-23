"""Config wiring for the SOME/IP one-to-many example."""

from __future__ import annotations

from examples.someip_pubsub_one_pub_many_subs.publisher import (
    parse_args as parse_publisher_args,
)
from examples.someip_pubsub_one_pub_many_subs.service_contract import (
    EVENT_MAPPINGS,
    SERVICE_ID,
    TOPIC,
    publisher_config,
    subscriber_config,
)
from examples.someip_pubsub_one_pub_many_subs.subscriber import (
    parse_args as parse_subscriber_args,
)
from tinysoa.eventbus import SomeIPService, TopicPublisher, TopicSubscriber


def test_publisher_service_exposes_topic_views() -> None:
    service = SomeIPService(
        publisher_config(30920),
        event_mappings=EVENT_MAPPINGS,
        is_publisher=True,
    )
    assert isinstance(service.publisher(TOPIC), TopicPublisher)
    assert service.event_bus is not None
    assert service.event_bus.mappings[TOPIC].service_id == SERVICE_ID


def test_subscriber_service_exposes_topic_views() -> None:
    service = SomeIPService(
        subscriber_config(30931),
        event_mappings=EVENT_MAPPINGS,
        is_publisher=False,
    )

    async def _handler(_message):
        return None

    assert isinstance(service.subscriber(TOPIC, _handler), TopicSubscriber)
    assert service.event_bus is not None
    assert service.event_bus.mappings[TOPIC].service_id == SERVICE_ID


def test_publisher_cli_defaults() -> None:
    args = parse_publisher_args([])
    assert args.count == 20
    assert args.interval == 1.0


def test_subscriber_cli_defaults() -> None:
    args = parse_subscriber_args(["sub-1"])
    assert args.subscriber_id == "sub-1"
    assert args.want == 3
    assert args.local_port == 30930
