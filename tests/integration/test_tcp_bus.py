"""Tests for TCPEventBusBroker and the asyncio-native TCPEventBus client."""

from __future__ import annotations

import asyncio

import pytest

from tinysoa.core.errors import StateError
from tinysoa.eventbus import (
    TCPEventBus,
    TCPEventBusBroker,
    TCPEventBusClient,
    TCPEventBusServer,
    Topology,
)
from tinysoa.eventbus.message import EventMessage

pytestmark = pytest.mark.network


class TestTCPBrokerLifecycle:
    def test_broker_starts_and_stops_cleanly(self) -> None:
        broker = TCPEventBusBroker(host="127.0.0.1", port=0)
        broker.start()
        try:
            assert broker._server_sock is not None
            assert broker.port != 0
        finally:
            broker.stop()
        assert broker._server_sock is None

    def test_broker_stop_is_idempotent(self) -> None:
        broker = TCPEventBusBroker(host="127.0.0.1", port=0)
        broker.start()
        broker.stop()
        broker.stop()  # must not raise


class TestTCPClientLifecycle:
    async def test_client_start_stop(self) -> None:
        broker = TCPEventBusBroker(host="127.0.0.1", port=0)
        broker.start()
        bus = TCPEventBus(host="127.0.0.1", port=broker.port)
        try:
            await bus.start()
            assert bus.is_started
            await bus.stop()
            await bus.stop()  # idempotent
            assert not bus.is_started
        finally:
            await bus.stop()
            broker.stop()

    async def test_publish_before_start_raises(self) -> None:
        bus = TCPEventBus(host="127.0.0.1", port=1)
        with pytest.raises(StateError):
            await bus.publish(EventMessage(topic="test.tcp", payload={}))
        with pytest.raises(StateError):
            bus.subscribe("test.tcp", _noop_handler)


class TestTCPPubSubDelivery:
    async def test_publish_subscribe_delivers_message(self) -> None:
        broker = TCPEventBusBroker(host="127.0.0.1", port=0)
        broker.start()
        sub_bus = TCPEventBus(host="127.0.0.1", port=broker.port)
        pub_bus = TCPEventBus(host="127.0.0.1", port=broker.port)
        try:
            await sub_bus.start()
            await pub_bus.start()

            received: list[EventMessage] = []
            delivered = asyncio.Event()

            async def handler(message: EventMessage) -> None:
                received.append(message)
                delivered.set()

            sub = sub_bus.subscribe("test.tcp", handler)
            await asyncio.sleep(0.3)  # let the subscription reach the broker

            message = EventMessage(topic="test.tcp", payload={"v": 1})
            await pub_bus.publish(message)
            await asyncio.wait_for(delivered.wait(), timeout=2.0)

            assert len(received) == 1
            assert received[0].topic == "test.tcp"
            assert received[0].payload == {"v": 1}

            sub_bus.unsubscribe(sub)
            assert sub_bus.get_subscribers_count("test.tcp") == 0
        finally:
            await sub_bus.stop()
            await pub_bus.stop()
            broker.stop()


class TestTCPNamingAndTopology:
    def test_legacy_aliases_still_resolve(self) -> None:
        assert TCPEventBusClient is TCPEventBus
        assert TCPEventBusServer is TCPEventBusBroker

    def test_topology_is_broker(self) -> None:
        assert TCPEventBus.topology is Topology.BROKER
        assert TCPEventBusBroker.topology is Topology.BROKER


async def _noop_handler(_message: EventMessage) -> None:
    return None
