"""Config wiring for the SOME/IP one-to-one example."""

from __future__ import annotations

from examples.someip_pubsub_one_pub_one_sub import (
    publisher,
    service_contract,
    subscriber,
)
from examples.someip_pubsub_one_pub_one_sub.publisher import (
    parse_args as parse_publisher_args,
)
from examples.someip_pubsub_one_pub_one_sub.subscriber import (
    parse_args as parse_subscriber_args,
)
from tinysoa.eventbus import SomeIPService, TopicPublisher, TopicSubscriber


def test_publisher_and_subscriber_use_the_shared_service_contract() -> None:
    assert publisher.TOPIC == service_contract.TOPIC
    assert subscriber.TOPIC == service_contract.TOPIC
    assert publisher.EVENT_MAPPINGS is service_contract.EVENT_MAPPINGS
    assert subscriber.EVENT_MAPPINGS is service_contract.EVENT_MAPPINGS

    mapping = service_contract.EVENT_MAPPINGS[service_contract.TOPIC]
    assert mapping.service_id == service_contract.SERVICE_ID
    assert mapping.instance_id == service_contract.INSTANCE_ID
    assert mapping.eventgroup_id == service_contract.EVENTGROUP_ID


def test_publisher_service_exposes_topic_views() -> None:
    service = SomeIPService(
        service_contract.publisher_config(service_contract.PUBLISHER_PORT),
        event_mappings=service_contract.EVENT_MAPPINGS,
        is_publisher=True,
    )

    assert isinstance(service.publisher(publisher.TOPIC), TopicPublisher)
    assert service.event_bus is not None
    assert (
        service.event_bus.mappings[publisher.TOPIC].service_id
        == service_contract.SERVICE_ID
    )


def test_subscriber_service_exposes_topic_views() -> None:
    service = SomeIPService(
        service_contract.subscriber_config(30981),
        event_mappings=service_contract.EVENT_MAPPINGS,
        is_publisher=False,
    )

    async def _handler(_message):
        return None

    assert isinstance(service.subscriber(subscriber.TOPIC, _handler), TopicSubscriber)
    assert service.event_bus is not None
    assert (
        service.event_bus.mappings[subscriber.TOPIC].service_id
        == service_contract.SERVICE_ID
    )


def test_publisher_cli_defaults() -> None:
    args = parse_publisher_args([])
    assert args.count == 20
    assert args.interval == 1.0


def test_subscriber_cli_defaults() -> None:
    args = parse_subscriber_args([])
    assert args.want == 3
    assert args.local_port == 30980
