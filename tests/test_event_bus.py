import pytest
import time
import asyncio
from uuid import uuid4
from threading import Thread

from tinysoa.eventbus.message import EventMessage
from tinysoa.eventbus.bus import (
    InMemoryEventBus,
    Subscription,
    TopicMatcher,
    get_event_bus,
    set_event_bus,
)


def test_event_message_creation():
    msg = EventMessage(topic="user.created", payload={"user_id": 123})
    
    assert msg.topic == "user.created"
    assert msg.payload["user_id"] == 123
    assert msg.message_id is not None
    assert msg.timestamp is not None
    assert msg.content_type == "application/json"


def test_event_message_with_metadata():
    trace_id = uuid4()
    correlation_id = uuid4()
    
    msg = EventMessage(
        topic="order.placed",
        payload={"order_id": 456},
        headers={"x-user": "alice"},
        trace_id=trace_id,
        correlation_id=correlation_id,
    )
    
    assert msg.headers["x-user"] == "alice"
    assert msg.trace_id == trace_id
    assert msg.correlation_id == correlation_id


def test_event_message_serialization():
    msg = EventMessage(
        topic="test.event",
        payload={"data": "value"},
        headers={"key": "val"},
    )
    
    # To dict
    data = msg.to_dict()
    assert data["topic"] == "test.event"
    assert data["payload"]["data"] == "value"
    assert "message_id" in data
    assert "timestamp" in data
    
    # From dict
    restored = EventMessage.from_dict(data)
    assert restored.topic == msg.topic
    assert restored.payload == msg.payload
    assert restored.message_id == msg.message_id


def test_event_message_json_serialization():
    msg = EventMessage(topic="test", payload={"num": 42})
    
    json_str = msg.to_json()
    assert isinstance(json_str, str)
    assert "test" in json_str
    
    restored = EventMessage.from_json(json_str)
    assert restored.topic == "test"
    assert restored.payload["num"] == 42


@pytest.mark.asyncio
async def test_eventbus_publish_subscribe():
    bus = InMemoryEventBus()
    
    received = []
    
    async def handler(msg: EventMessage):
        received.append(msg.payload)
    
    # Subscribe
    sub = bus.subscribe("test.topic", handler)
    assert isinstance(sub, Subscription)
    assert bus.get_subscribers_count("test.topic") == 1
    
    # Publish
    msg = EventMessage(topic="test.topic", payload={"data": "hello"})
    await bus.publish(msg)
    
    # Verify delivery
    assert len(received) == 1
    assert received[0]["data"] == "hello"


@pytest.mark.asyncio
async def test_eventbus_multiple_subscribers():
    bus = InMemoryEventBus()
    
    received1 = []
    received2 = []
    
    async def h1(msg): received1.append(msg.payload)
    async def h2(msg): received2.append(msg.payload)

    bus.subscribe("topic", h1)
    bus.subscribe("topic", h2)
    
    assert bus.get_subscribers_count("topic") == 2
    
    msg = EventMessage(topic="topic", payload={"value": 123})
    await bus.publish(msg)
    
    # Both should receive
    assert len(received1) == 1
    assert len(received2) == 1
    assert received1[0]["value"] == 123
    assert received2[0]["value"] == 123


@pytest.mark.asyncio
async def test_eventbus_topic_isolation():
    bus = InMemoryEventBus()
    
    topic1_received = []
    topic2_received = []
    
    async def h1(msg): topic1_received.append(msg)
    async def h2(msg): topic2_received.append(msg)

    bus.subscribe("topic1", h1)
    bus.subscribe("topic2", h2)
    
    # Publish to topic1
    await bus.publish(EventMessage(topic="topic1", payload={"a": 1}))
    
    # Only topic1 subscriber should receive
    assert len(topic1_received) == 1
    assert len(topic2_received) == 0
    
    # Publish to topic2
    await bus.publish(EventMessage(topic="topic2", payload={"b": 2}))
    
    # Now topic2 also has one
    assert len(topic1_received) == 1
    assert len(topic2_received) == 1


@pytest.mark.asyncio
async def test_eventbus_unsubscribe():
    bus = InMemoryEventBus()
    
    received = []
    
    async def h(msg): received.append(msg.payload)

    sub = bus.subscribe("topic", h)
    
    # Publish first message
    await bus.publish(EventMessage(topic="topic", payload={"seq": 1}))
    assert len(received) == 1
    
    # Unsubscribe
    bus.unsubscribe(sub)
    assert bus.get_subscribers_count("topic") == 0
    
    # Publish second message
    await bus.publish(EventMessage(topic="topic", payload={"seq": 2}))
    
    # Should not receive
    assert len(received) == 1


@pytest.mark.asyncio
async def test_eventbus_error_handling():
    bus = InMemoryEventBus()
    
    async def failing_handler(msg: EventMessage):
        raise Exception("Handler error")
    
    received_ok = []
    
    async def ok_handler(msg: EventMessage):
        received_ok.append(msg.payload)
    
    # Subscribe both handlers
    bus.subscribe("topic", failing_handler)
    bus.subscribe("topic", ok_handler)
    
    # Publish - should not crash even if one handler fails
    await bus.publish(EventMessage(topic="topic", payload={"data": "test"}))
    
    # OK handler should still receive
    assert len(received_ok) == 1
    
    # Metrics should track error
    metrics = bus.get_metrics()
    assert metrics["errors"] == 1


@pytest.mark.asyncio
async def test_eventbus_metrics():
    bus = InMemoryEventBus(enable_metrics=True)
    
    async def noop(msg): pass

    bus.subscribe("topic1", noop)
    bus.subscribe("topic1", noop)
    bus.subscribe("topic2", noop)
    
    await bus.publish(EventMessage(topic="topic1", payload={}))
    await bus.publish(EventMessage(topic="topic2", payload={}))
    
    async def noop(msg): pass

    bus.subscribe("topic.a", noop)
    bus.subscribe("topic.b", noop)
    bus.subscribe("topic.c", noop)
    
    topics = bus.get_all_topics()
    assert len(topics) == 5
    assert "topic.a" in topics
    assert "topic.b" in topics
    assert "topic.c" in topics


def test_eventbus_clear_all_subscriptions():
    bus = InMemoryEventBus()
    
    async def noop(msg): pass

    bus.subscribe("topic1", noop)
    bus.subscribe("topic2", noop)
    
    assert len(bus.get_all_topics()) == 2
    
    bus.clear_all_subscriptions()
    
    assert len(bus.get_all_topics()) == 0
    assert bus.get_subscribers_count("topic1") == 0


@pytest.mark.asyncio
async def test_eventbus_concurrent_publish():
    """Test that concurrent publishes don't cause issues."""
    bus = InMemoryEventBus()
    
    received = []
    
    async def handler(msg: EventMessage):
        received.append(msg.payload["seq"])
    
    bus.subscribe("concurrent", handler)
    
    async def publish_messages(start, count):
        for i in range(start, start + count):
            msg = EventMessage(topic="concurrent", payload={"seq": i})
            await bus.publish(msg)
    
    # Publish from multiple tasks
    tasks = [
        asyncio.create_task(publish_messages(0, 10)),
        asyncio.create_task(publish_messages(10, 10)),
        asyncio.create_task(publish_messages(20, 10)),
    ]
    
    await asyncio.gather(*tasks)
    
    # Should have received all 30 messages
    assert len(received) == 30
    assert set(received) == set(range(30))


def test_topic_matcher():
    assert TopicMatcher.matches("user.created", "user.created") is True
    assert TopicMatcher.matches("user.created", "user.updated") is False
    
    assert TopicMatcher.match_any("test", ["foo", "bar", "test"]) is True
    assert TopicMatcher.match_any("test", ["foo", "bar"]) is False


def test_global_event_bus():
    bus1 = get_event_bus()
    bus2 = get_event_bus()
    
    # Should be same instance
    assert bus1 is bus2
    
    # Can set custom bus
    custom_bus = InMemoryEventBus()
    set_event_bus(custom_bus)
    
    bus3 = get_event_bus()
    assert bus3 is custom_bus

@pytest.mark.asyncio
async def test_eventbus_stress():
    """Simple stress test to check for resource leaks."""
    bus = InMemoryEventBus()
    
    received_count = [0]
    
    async def handler(msg: EventMessage):
        received_count[0] += 1
    
    bus.subscribe("stress", handler)
    
    # Publish many messages
    for i in range(1000):
        await bus.publish(EventMessage(topic="stress", payload={"seq": i}))
    
    assert received_count[0] == 1000
    
    metrics = bus.get_metrics()
    assert metrics["published"] == 1000
    assert metrics["delivered"] == 1000
