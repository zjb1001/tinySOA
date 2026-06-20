import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure tinysoa package is importable when running tests directly
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from someip.config import Eventgroup
from someip.header import L4Protocols
from someip.sd import ServiceDiscoveryProtocol, Timings
from tinysoa.eventbus.someip import SomeIPSubscriber


class _FakeTransport:
    def __init__(self, sockname):
        self._sockname = sockname
        self.closed = False

    def get_extra_info(self, name, default=None):
        if name == "sockname":
            return self._sockname
        return default

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_proto002_rxsd_uses_unicast_endpoint():
    """PROTO-002: subscriber advertises a concrete unicast endpoint for RxSD responses."""
    discovery = SimpleNamespace(find_subscribe_eventgroup=MagicMock())
    sd_stub = SimpleNamespace(discovery=discovery)
    subscriber = SomeIPSubscriber(local_addr="127.0.0.1", sd_protocol=sd_stub)
    await subscriber.start()

    sockname = ("127.0.0.1", 40123)

    async def fake_cde(factory, local_addr):
        factory()
        return _FakeTransport(sockname), None

    loop = asyncio.get_event_loop()
    with patch.object(loop, "create_datagram_endpoint", new=AsyncMock(side_effect=fake_cde)):
        await subscriber.subscribe(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x000A,
            major_version=1,
            on_notification=AsyncMock(),
        )

    assert discovery.find_subscribe_eventgroup.call_count == 1
    evgrp = discovery.find_subscribe_eventgroup.call_args.args[0]
    assert evgrp.service_id == 0x1234
    assert evgrp.instance_id == 0x0001
    assert evgrp.eventgroup_id == 0x000A
    assert evgrp.protocol == L4Protocols.UDP
    assert evgrp.sockname == sockname

    subscriber.stop()


@pytest.mark.asyncio
async def test_proto005_builds_sd_subscribe_entry():
    """PROTO-005: subscribe builds correct Eventgroup and triggers SD find/subscribe."""
    calls = []

    def record(evgrp):
        calls.append(evgrp)

    discovery = SimpleNamespace(find_subscribe_eventgroup=MagicMock(side_effect=record))
    sd_stub = SimpleNamespace(discovery=discovery)
    subscriber = SomeIPSubscriber(local_addr="127.0.0.1", sd_protocol=sd_stub)
    await subscriber.start()

    async def fake_cde(factory, local_addr):
        factory()
        return _FakeTransport(("127.0.0.1", 40124)), None

    loop = asyncio.get_event_loop()
    with patch.object(loop, "create_datagram_endpoint", new=AsyncMock(side_effect=fake_cde)):
        await subscriber.subscribe(
            service_id=0x2345,
            instance_id=0x0002,
            eventgroup_id=0x000B,
            major_version=2,
            on_notification=AsyncMock(),
        )

    assert len(calls) == 1
    evgrp = calls[0]
    assert evgrp.service_id == 0x2345
    assert evgrp.instance_id == 0x0002
    assert evgrp.eventgroup_id == 0x000B
    assert evgrp.major_version == 2
    assert evgrp.sockname[1] != 0

    subscriber.stop()


@pytest.mark.asyncio
async def test_proto006_allows_multiple_clients_subscribing_same_eventgroup():
    """PROTO-006: two subscribers get independent endpoints for the same eventgroup."""
    calls = []

    def record(evgrp):
        calls.append(evgrp)

    discovery = SimpleNamespace(find_subscribe_eventgroup=MagicMock(side_effect=record))
    sd_stub = SimpleNamespace(discovery=discovery)

    loop = asyncio.get_event_loop()
    transports = [
        (_FakeTransport(("127.0.0.1", 40130)), None),
        (_FakeTransport(("127.0.0.1", 40131)), None),
    ]

    async def fake_cde_factory():
        for trsp, proto in transports:
            yield trsp, proto

    transport_iter = fake_cde_factory().__aiter__()

    async def fake_cde(factory, local_addr):
        factory()
        return await transport_iter.__anext__()

    with patch.object(loop, "create_datagram_endpoint", new=AsyncMock(side_effect=fake_cde)):
        subscriber_a = SomeIPSubscriber(local_addr="127.0.0.1", sd_protocol=sd_stub)
        subscriber_b = SomeIPSubscriber(local_addr="127.0.0.1", sd_protocol=sd_stub)
        await subscriber_a.start()
        await subscriber_b.start()

        await subscriber_a.subscribe(
            service_id=0x3456,
            instance_id=0x0003,
            eventgroup_id=0x000C,
            major_version=1,
            on_notification=AsyncMock(),
        )
        await subscriber_b.subscribe(
            service_id=0x3456,
            instance_id=0x0003,
            eventgroup_id=0x000C,
            major_version=1,
            on_notification=AsyncMock(),
        )

    assert len(calls) == 2
    socknames = {evgrp.sockname for evgrp in calls}
    assert len(socknames) == 2

    subscriber_a.stop()
    subscriber_b.stop()


@pytest.mark.asyncio
async def test_proto008_subscription_refreshes_until_stopped():
    """PROTO-008: subscriber refreshes before TTL expiry and sends stop on teardown."""
    timings = Timings(
        INITIAL_DELAY_MIN=0,
        INITIAL_DELAY_MAX=0,
        REQUEST_RESPONSE_DELAY_MIN=0,
        REQUEST_RESPONSE_DELAY_MAX=0,
        REPETITIONS_MAX=1,
        REPETITIONS_BASE_DELAY=0.001,
        CYCLIC_OFFER_DELAY=0.01,
        FIND_TTL=1,
        ANNOUNCE_TTL=1,
        SUBSCRIBE_TTL=1,
        SUBSCRIBE_REFRESH_INTERVAL=0.05,
        SEND_COLLECTION_TIMEOUT=0.001,
    )

    sd = ServiceDiscoveryProtocol(("224.224.224.245", 30490), timings=timings)
    sent_entries = []

    def fake_send_sd(entries, remote=None):
        sent_entries.extend(entries)

    sd.send_sd = fake_send_sd

    evgrp = Eventgroup(
        service_id=0x4567,
        instance_id=0x0004,
        major_version=1,
        eventgroup_id=0x000D,
        sockname=("127.0.0.1", 40140),
        protocol=L4Protocols.UDP,
    )

    sd.subscriber.subscribe_eventgroup(evgrp, ("127.0.0.1", 30490))
    sd.subscriber.start()

    await asyncio.sleep(0.12)
    sd.subscriber.stop()
    await asyncio.sleep(0)

    assert len(sent_entries) >= 2
    ttl_values = [entry.ttl for entry in sent_entries]
    assert all(ttl == timings.SUBSCRIBE_TTL for ttl in ttl_values[:-1])
    assert ttl_values[-1] == 0
