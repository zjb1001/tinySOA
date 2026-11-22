"""Contract tests for the EventBus abstraction itself."""

from __future__ import annotations

import pytest

from tinysoa.eventbus import (
    EventBus,
    EventBusBroker,
    InMemoryEventBus,
    ManagedEventBus,
    MessageStream,
    SomeIPEventBus,
    TCPEventBus,
    TCPEventBusBroker,
    TCPMessageStream,
    Topology,
)


def test_topology_has_three_deployment_models() -> None:
    assert {member.value for member in Topology} == {"local", "broker", "peer"}


def test_eventbus_core_contract_is_four_methods() -> None:
    assert EventBus.__abstractmethods__ == {
        "publish",
        "subscribe",
        "unsubscribe",
        "get_subscribers_count",
    }


def test_eventbus_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        EventBus()  # type: ignore[abstract]


def test_managed_eventbus_adds_start_stop() -> None:
    assert {"start", "stop"} <= ManagedEventBus.__abstractmethods__
    with pytest.raises(TypeError):
        ManagedEventBus()  # type: ignore[abstract]


def test_broker_contract_is_start_stop() -> None:
    assert EventBusBroker.__abstractmethods__ == {"start", "stop"}
    with pytest.raises(TypeError):
        EventBusBroker()  # type: ignore[abstract]


def test_implementations_declare_topology() -> None:
    assert InMemoryEventBus.topology is Topology.LOCAL
    assert TCPEventBus.topology is Topology.BROKER
    assert TCPEventBusBroker.topology is Topology.BROKER
    assert SomeIPEventBus is not None
    assert SomeIPEventBus.topology is Topology.PEER


def test_message_stream_contract_is_transport_only() -> None:
    assert MessageStream.__abstractmethods__ == {
        "open",
        "close",
        "write",
        "drain",
        "readline",
    }
    with pytest.raises(TypeError):
        MessageStream()  # type: ignore[abstract]


def test_tcp_event_bus_delegates_to_message_stream() -> None:
    bus = TCPEventBus(host="127.0.0.1", port=1)
    assert isinstance(bus._stream, TCPMessageStream)
    assert isinstance(bus._stream, MessageStream)
    assert bus._stream.is_open is False


async def test_inmemory_managed_lifecycle_is_a_noop() -> None:
    bus = InMemoryEventBus()
    await bus.start()
    await bus.stop()
    await bus.stop()  # idempotent
