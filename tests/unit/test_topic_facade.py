"""Application-facing TopicPublisher/TopicSubscriber and bus registration."""

from __future__ import annotations

import pytest

from tinysoa.core.errors import StateError, ValidationError
from tinysoa.eventbus import InMemoryEventBus


async def test_publisher_and_subscriber_register_with_bus() -> None:
    bus = InMemoryEventBus()
    await bus.start()
    received = []

    async def handler(message) -> None:
        received.append(message.payload)

    subscriber = bus.subscriber("demo.topic", handler)
    publisher = bus.publisher("demo.topic")

    assert not bus.is_registered(publisher)
    assert not bus.is_registered(subscriber)

    await bus.register(subscriber)
    await bus.register(publisher)
    await publisher.publish({"value": 1})

    assert received == [{"value": 1}]
    assert bus.is_registered(publisher)
    assert bus.has_registered_publisher("demo.topic")

    await bus.unregister(subscriber)
    await publisher.publish({"value": 2})
    assert received == [{"value": 1}]

    await bus.unregister(publisher)
    assert not bus.has_registered_publisher("demo.topic")
    await bus.stop()


async def test_publish_before_register_raises() -> None:
    bus = InMemoryEventBus()
    await bus.start()
    publisher = bus.publisher("demo.topic")

    with pytest.raises(StateError, match="not registered"):
        await publisher.publish({"value": 1})

    await bus.stop()


async def test_register_is_idempotent() -> None:
    bus = InMemoryEventBus()
    await bus.start()
    received = []

    async def handler(message) -> None:
        received.append(message.payload)

    subscriber = bus.subscriber("demo.topic", handler)
    publisher = bus.publisher("demo.topic")

    await bus.register(subscriber)
    await bus.register(subscriber)
    await bus.register(publisher)
    await bus.register(publisher)

    assert bus.get_subscribers_count("demo.topic") == 1
    assert bus.has_registered_publisher("demo.topic")

    await publisher.publish({"value": 1})
    assert received == [{"value": 1}]

    await bus.stop()


async def test_publisher_refcount_releases_topic_after_last_handle() -> None:
    bus = InMemoryEventBus()
    await bus.start()
    first = bus.publisher("demo.topic")
    second = bus.publisher("demo.topic")

    await bus.register(first)
    await bus.register(second)
    assert bus.has_registered_publisher("demo.topic")

    await bus.unregister(first)
    assert bus.has_registered_publisher("demo.topic")

    await bus.unregister(second)
    assert not bus.has_registered_publisher("demo.topic")
    await bus.stop()


async def test_participant_must_belong_to_the_bus() -> None:
    first = InMemoryEventBus()
    second = InMemoryEventBus()
    publisher = first.publisher("demo.topic")

    with pytest.raises(ValidationError, match="different bus"):
        await second.register(publisher)


def test_subscriber_requires_callable_handler() -> None:
    bus = InMemoryEventBus()
    with pytest.raises(ValidationError, match="callable"):
        bus.subscriber("demo.topic", object())  # type: ignore[arg-type]
