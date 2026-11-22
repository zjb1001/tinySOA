"""Contract tests for the shared SOME/IP endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tinysoa.eventbus import (
    SomeIPMethodDispatcher,
    SomeIPMethodInvoker,
    SomeIPPublisher,
    SomeIPServiceBinding,
)
from tinysoa.eventbus.someip import (
    SomeIPEndpoint,
    SomeIPEventBus,
    SomeIPServiceInstance,
    SomeIPTopicMapping,
)

MAPPINGS = {
    "sensor.temperature": SomeIPTopicMapping(
        service_id=0x1001, instance_id=0x0001, eventgroup_id=0x0001
    ),
    "sensor.humidity": SomeIPTopicMapping(
        service_id=0x1002, instance_id=0x0001, eventgroup_id=0x0001
    ),
}


def test_event_bus_owns_one_shared_endpoint() -> None:
    bus = SomeIPEventBus(MAPPINGS, local_ip="127.0.0.1", publisher_port=30600)
    assert isinstance(bus._endpoint, SomeIPEndpoint)
    assert bus.local_ip == bus._endpoint.local_ip
    assert bus.publisher_port_base == bus._endpoint.publisher_port_base
    assert bus._service_ports is bus._endpoint.service_ports
    assert bus._publishers is bus._endpoint.publishers


async def test_event_bus_delegates_start_and_stop() -> None:
    bus = SomeIPEventBus(MAPPINGS, publisher_port=30610)
    start = AsyncMock()
    stop = AsyncMock()
    bus._endpoint.start = start  # type: ignore[method-assign]
    bus._endpoint.stop = stop  # type: ignore[method-assign]

    await bus.start()
    start.assert_awaited_once()

    bus._started = True
    await bus.stop()
    stop.assert_awaited_once()


async def test_endpoint_subscribe_requires_start() -> None:
    endpoint = SomeIPEndpoint()

    async def handler(_payload: bytes) -> None:
        return None

    with pytest.raises(RuntimeError, match="not started"):
        await endpoint.subscribe(
            service_id=1,
            instance_id=1,
            eventgroup_id=1,
            major_version=1,
            on_notification=handler,
        )


def test_endpoint_reuses_one_service_instance() -> None:
    endpoint = SomeIPEndpoint(publisher_port=30700)
    first = endpoint.get_or_create_service_instance(
        0x1234, 0x0001, major_version=1, port=0
    )
    second = endpoint.get_or_create_service_instance(
        0x1234, 0x0001, major_version=1, port=0
    )
    other = endpoint.get_or_create_service_instance(
        0x5678, 0x0001, major_version=1, port=0
    )
    assert isinstance(first, SomeIPServiceInstance)
    assert first is second
    assert other is not first
    assert endpoint.services[(0x1234, 0x0001)] is first
    assert endpoint.service_ports[(0x1234, 0x0001)] == 0


def test_publisher_can_share_a_service_instance() -> None:
    endpoint = SomeIPEndpoint(publisher_port=30710)
    instance = endpoint.get_or_create_service_instance(
        0x1234, 0x0001, major_version=1, port=0
    )
    publisher = SomeIPPublisher(
        service_id=0x1234,
        instance_id=0x0001,
        major_version=1,
        local_addr="127.0.0.1",
        port=0,
        instance=instance,
    )

    async def handler(_payload: bytes) -> None:
        return None

    instance.register_method(0x0001, lambda _msg, _addr: None)
    instance.add_eventgroup(0x0001, handler)

    assert publisher._instance is instance
    assert publisher.service is None
    assert instance._pending_methods
    assert instance._pending_eventgroups


def test_event_method_and_invoker_can_share_one_endpoint() -> None:
    endpoint = SomeIPEndpoint(publisher_port=30720)
    binding = SomeIPServiceBinding(
        name="calc",
        service_id=0x4444,
        instance_id=0x0001,
        methods={"add": 1},
    )

    bus = SomeIPEventBus({}, endpoint=endpoint)
    dispatcher = SomeIPMethodDispatcher(binding, endpoint=endpoint)
    invoker = SomeIPMethodInvoker(binding, endpoint=endpoint)

    assert bus._endpoint is endpoint
    assert dispatcher._endpoint is endpoint
    assert invoker._endpoint is endpoint
    assert bus._owns_endpoint is False
    assert dispatcher._owns_endpoint is False
    assert invoker._owns_endpoint is False
