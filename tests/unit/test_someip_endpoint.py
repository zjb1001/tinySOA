"""Contract tests for the shared SOME/IP endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tinysoa.eventbus.someip import (
    SomeIPEndpoint,
    SomeIPEventBus,
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
