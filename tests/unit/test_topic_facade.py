"""Application-facing TopicPublisher/TopicSubscriber facade."""

from __future__ import annotations

from tinysoa.eventbus import InMemoryEventBus


async def test_publisher_and_subscriber_facade() -> None:
    bus = InMemoryEventBus()
    await bus.start()
    received = []

    async def handler(message) -> None:
        received.append(message.payload)

    subscriber = bus.subscriber("demo.topic")
    subscription = subscriber.on(handler)
    publisher = bus.publisher("demo.topic")

    await publisher.register()
    await publisher.publish({"value": 1})

    assert received == [{"value": 1}]

    subscriber.off(subscription)
    await publisher.publish({"value": 2})
    assert received == [{"value": 1}]

    await bus.stop()
