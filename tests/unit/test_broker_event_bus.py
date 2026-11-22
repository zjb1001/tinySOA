"""Unit tests for BrokerEventBus using an in-memory MessageStream."""

from __future__ import annotations

import asyncio

import pytest

from tinysoa.core.errors import StateError
from tinysoa.eventbus import BrokerEventBus, EventMessage, MessageStream


class RecordingStream(MessageStream):
    """A MessageStream that records writes and never yields inbound frames."""

    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.drained = False
        self.frames: list[bytes] = []
        self._never = asyncio.Event()

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    def write(self, frame: bytes) -> None:
        self.frames.append(frame)

    async def drain(self) -> None:
        self.drained = True

    async def readline(self) -> bytes:
        await self._never.wait()
        return b""  # pragma: no cover - stop() cancels the reader task


async def test_broker_event_bus_uses_injected_stream() -> None:
    stream = RecordingStream()
    bus = BrokerEventBus(stream, name="unit-test")
    await bus.start()

    async def handler(_message: EventMessage) -> None:
        return None

    sub = bus.subscribe("demo.topic", handler)
    assert bus.get_subscribers_count("demo.topic") == 1

    await bus.publish(EventMessage(topic="demo.topic", payload={"v": 1}))
    bus.unsubscribe(sub)
    assert bus.get_subscribers_count("demo.topic") == 0

    await bus.stop()

    assert stream.opened is True
    assert stream.closed is True
    assert stream.drained is True
    assert any(b'"action": "subscribe"' in frame for frame in stream.frames)
    assert any(b'"action": "publish"' in frame for frame in stream.frames)
    assert any(b'"action": "unsubscribe"' in frame for frame in stream.frames)


async def test_broker_event_bus_rejects_use_before_start() -> None:
    bus = BrokerEventBus(RecordingStream(), name="unit-test")
    with pytest.raises(StateError):
        await bus.publish(EventMessage(topic="demo.topic", payload={}))
    with pytest.raises(StateError):
        bus.subscribe("demo.topic", _noop_handler)


async def _noop_handler(_message: EventMessage) -> None:
    return None
