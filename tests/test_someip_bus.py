import pytest
import json
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from tinysoa.eventbus.someip import (
    SomeIPEventBus, 
    SomeIPTopicMapping,
    SomeIPPublisher,
    SomeIPSubscriber,
    SomeIPEventgroupAdapter
)
from tinysoa.eventbus.message import EventMessage


@pytest.mark.asyncio
async def test_someip_bus_initialization():
    """Test SOME/IP bus can be initialized."""
    mappings = {
        "test.topic": SomeIPTopicMapping(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x0001,
            major_version=1
        )
    }
    bus = SomeIPEventBus(mappings, local_ip="127.0.0.1", publisher_port=30490)
    assert bus.mappings == mappings
    assert bus.local_ip == "127.0.0.1"
    assert not bus._started


@pytest.mark.asyncio
async def test_someip_bus_serialization():
    """Test message serialization/deserialization."""
    mappings = {
        "test.topic": SomeIPTopicMapping(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    bus = SomeIPEventBus(mappings)
    
    msg = EventMessage(topic="test.topic", payload={"foo": "bar"})
    
    # Test Serialization
    payload_bytes = bus._serialize_message(msg)
    assert isinstance(payload_bytes, bytes)
    
    # Test Deserialization
    decoded_msg = bus._deserialize_message(payload_bytes)
    assert decoded_msg.topic == msg.topic
    assert decoded_msg.payload == msg.payload
    assert decoded_msg.message_id == msg.message_id


@pytest.mark.asyncio
async def test_someip_publisher_initialization():
    """Test SOME/IP publisher creation."""
    publisher = SomeIPPublisher(
        service_id=0x1234,
        instance_id=0x0001,
        major_version=1,
        local_addr="127.0.0.1",
        port=30490
    )
    assert publisher.service_id == 0x1234
    assert publisher.instance_id == 0x0001
    assert publisher.major_version == 1
    assert publisher._service is None


@pytest.mark.asyncio
async def test_someip_subscriber_initialization():
    """Test SOME/IP subscriber creation."""
    subscriber = SomeIPSubscriber(local_addr="127.0.0.1")
    assert subscriber.local_addr == "127.0.0.1"
    assert subscriber._sd_prot is None


@pytest.mark.asyncio
async def test_someip_bus_subscribe_without_start():
    """Test that subscribing without starting raises error."""
    mappings = {
        "test.topic": SomeIPTopicMapping(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    bus = SomeIPEventBus(mappings)
    
    async def handler(msg):
        pass
    
    # Should raise RuntimeError because bus not started
    with pytest.raises(RuntimeError, match="not started"):
        bus.subscribe("test.topic", handler)


@pytest.mark.asyncio
async def test_someip_bus_unknown_mapping():
    """Test handling of unknown topic mappings."""
    mappings = {
        "test.topic": SomeIPTopicMapping(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    bus = SomeIPEventBus(mappings)
    bus._started = True  # Simulate started state
    
    # Publishing to unknown topic should log warning
    msg = EventMessage(topic="unknown", payload="data")
    await bus.publish(msg)
    # Should not raise
    
    # Subscribing to unknown topic should raise
    async def handler(msg):
        pass
    
    with pytest.raises(ValueError, match="No SOME/IP mapping"):
        bus.subscribe("unknown", handler)


@pytest.mark.asyncio
async def test_someip_bus_subscription_count():
    """Test tracking subscription count."""
    mappings = {
        "test.topic": SomeIPTopicMapping(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    bus = SomeIPEventBus(mappings)
    bus._started = True
    
    # Mock the subscriber
    bus._subscriber = MagicMock()
    
    async def handler(msg):
        pass
    
    # Subscribe first time
    with patch('asyncio.create_task'):
        sub1 = bus.subscribe("test.topic", handler)
    
    assert bus.get_subscribers_count("test.topic") == 1
    
    # Subscribe second time
    with patch('asyncio.create_task'):
        sub2 = bus.subscribe("test.topic", handler)
    
    assert bus.get_subscribers_count("test.topic") == 2
    
    # Unsubscribe
    bus.unsubscribe(sub1)
    assert bus.get_subscribers_count("test.topic") == 1
    
    bus.unsubscribe(sub2)
    assert bus.get_subscribers_count("test.topic") == 0


@pytest.mark.asyncio
async def test_someip_topic_mapping():
    """Test SOME/IP topic mapping configuration."""
    mapping = SomeIPTopicMapping(
        service_id=0x1234,
        instance_id=0x5678,
        eventgroup_id=0x0001,
        major_version=1,
        minor_version=0,
        event_id=0x0001,
        l4_protocol="UDP"
    )
    
    assert mapping.service_id == 0x1234
    assert mapping.instance_id == 0x5678
    assert mapping.eventgroup_id == 0x0001
    assert mapping.major_version == 1
    assert mapping.minor_version == 0
    assert mapping.event_id == 0x0001
    assert mapping.l4_protocol == "UDP"

