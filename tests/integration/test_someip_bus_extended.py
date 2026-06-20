import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tinysoa.eventbus.message import EventMessage
from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping, SomeIPPublisher


@pytest.mark.asyncio
async def test_publish_triggers_start_and_notify():
    mappings = {
        "sensor.temp": SomeIPTopicMapping(service_id=0x1001, instance_id=0x0001, eventgroup_id=0x000A)
    }
    bus = SomeIPEventBus(mappings, local_ip="127.0.0.1", publisher_port=30500)
    bus._started = True

    msg = EventMessage(topic="sensor.temp", payload={"t": 25.5})

    # Patch SomeIPPublisher.start and notify
    with patch.object(SomeIPPublisher, "start", new=AsyncMock()) as mock_start, \
         patch.object(SomeIPPublisher, "notify", new=AsyncMock()) as mock_notify:
        await bus.publish(msg)

        # Publisher created and started once; notify called with encoded payload
        assert mock_start.await_count == 1
        assert mock_notify.await_count == 1
        args, kwargs = mock_notify.await_args
        # eventgroup_id, event_id, payload_bytes
        assert args[0] == mappings["sensor.temp"].eventgroup_id
        assert isinstance(args[2], bytes)


@pytest.mark.asyncio
async def test_subscribe_dispatches_on_notification_to_handlers():
    mappings = {
        "sensor.humidity": SomeIPTopicMapping(service_id=0x1002, instance_id=0x0002, eventgroup_id=0x000B)
    }
    bus = SomeIPEventBus(mappings)
    bus._started = True

    # Fake subscriber to capture on_notification closure
    captured_handler = {}

    async def fake_subscribe(service_id, instance_id, eventgroup_id, major_version, on_notification):
        captured_handler[(service_id, instance_id, eventgroup_id)] = on_notification

    bus._subscriber = MagicMock()
    bus._subscriber.subscribe = AsyncMock(side_effect=fake_subscribe)

    received = []

    async def handler(msg: EventMessage):
        received.append(msg)

    # Avoid actual delay inside _start_subscription
    with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        # Directly invoke _start_subscription to make the test deterministic
        mapping = mappings["sensor.humidity"]
        await bus._start_subscription(mapping, "sensor.humidity", seq_num=0)

    # Register local handler
    sub = bus.subscribe("sensor.humidity", handler)

    # Simulate an incoming SOME/IP notification
    payload = bus._serialize_message(EventMessage(topic="sensor.humidity", payload={"h": 45}))
    key = (mapping.service_id, mapping.instance_id, mapping.eventgroup_id)
    assert key in captured_handler

    await captured_handler[key](payload)

    assert len(received) == 1
    assert received[0].topic == "sensor.humidity"
    assert received[0].payload == {"h": 45}


@pytest.mark.asyncio
async def test_unsubscribe_triggers_stop_subscription_when_last_subscriber_removed():
    mappings = {
        "sensor.pressure": SomeIPTopicMapping(service_id=0x1003, instance_id=0x0003, eventgroup_id=0x000C)
    }
    bus = SomeIPEventBus(mappings)
    bus._started = True
    bus._subscriber = MagicMock()

    async def dummy_handler(msg: EventMessage):
        pass

    # Patch _stop_subscription to observe invocation
    with patch.object(SomeIPEventBus, "_stop_subscription", new=AsyncMock()) as mock_stop:
        sub = bus.subscribe("sensor.pressure", dummy_handler)
        assert bus.get_subscribers_count("sensor.pressure") == 1
        bus.unsubscribe(sub)
        # _stop_subscription should be scheduled; since we patched it, verify awaited call possible
        # Allow event loop to process any scheduled tasks
        await asyncio.sleep(0)
        assert mock_stop.await_count == 1


def test_service_port_allocation_uniqueness():
    mappings = {
        "topic.a": SomeIPTopicMapping(service_id=0x2001, instance_id=0x0001, eventgroup_id=0x0010),
        "topic.b": SomeIPTopicMapping(service_id=0x2001, instance_id=0x0001, eventgroup_id=0x0011),
        "topic.c": SomeIPTopicMapping(service_id=0x2001, instance_id=0x0002, eventgroup_id=0x0012),
    }
    bus = SomeIPEventBus(mappings, publisher_port=30600)

    ports = bus._service_ports
    assert ports[(0x2001, 0x0001)] == ports[(0x2001, 0x0001)]
    assert ports[(0x2001, 0x0001)] != ports[(0x2001, 0x0002)]