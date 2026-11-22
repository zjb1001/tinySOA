from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Optional

from tinysoa.core.errors import StateError

from .bus import EventHandler, ManagedEventBus, Subscription, Topology
from .message import EventMessage
from .stream import MessageStream

logger = logging.getLogger(__name__)


class BrokerEventBus(ManagedEventBus):
    """EventBus client for the tinySOA broker wire protocol.

    Topology ``BROKER``.  The transport is an injected :class:`MessageStream`;
    this class owns subscription bookkeeping, the newline-delimited JSON
    control protocol, the reader task, and dispatch to async handlers.  It knows
    nothing about TCP or any other concrete transport.
    """

    topology = Topology.BROKER

    def __init__(self, stream: MessageStream, *, name: str = "broker"):
        self._stream = stream
        self._name = name
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._handlers: Dict[str, List[Subscription]] = {}
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Open the stream and start the reader task."""
        if self._started:
            return
        await self._stream.open()
        self._reader_task = asyncio.create_task(
            self._read_loop(),
            name=f"tinysoa-{self._name}-reader",
        )
        self._started = True

    async def stop(self) -> None:
        """Close the stream; safe to call more than once."""
        if not self._started and self._reader_task is None:
            return
        self._started = False
        reader_task, self._reader_task = self._reader_task, None
        if reader_task is not None:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
        await self._stream.close()
        self._handlers.clear()

    async def publish(self, message: EventMessage) -> None:
        """Send one event through the broker stream."""
        stream = self._require_stream()
        frame = {"action": "publish", "message": message.to_dict()}
        stream.write(json.dumps(frame).encode("utf-8") + b"\n")
        await stream.drain()

    def subscribe(self, topic: str, handler: EventHandler) -> Subscription:
        """Register a local handler and ask the broker for the topic."""
        stream = self._require_stream()
        subscription = Subscription.new(topic, handler)
        self._handlers.setdefault(topic, []).append(subscription)
        stream.write(
            json.dumps({"action": "subscribe", "topic": topic}).encode("utf-8") + b"\n"
        )
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a local handler and tell the broker to stop sending the topic.

        Cleanup is best-effort: after a disconnect the local handler is dropped
        without raising, so callers can always unwind safely.
        """
        handlers = self._handlers.get(subscription.topic, [])
        remaining = [sub for sub in handlers if sub.id != subscription.id]
        if remaining:
            self._handlers[subscription.topic] = remaining
        else:
            self._handlers.pop(subscription.topic, None)
        if not self._started:
            return
        try:
            self._stream.write(
                json.dumps(
                    {"action": "unsubscribe", "topic": subscription.topic}
                ).encode("utf-8")
                + b"\n"
            )
        except StateError:
            pass

    def get_subscribers_count(self, topic: str) -> int:
        """Return the number of *local* handlers for a topic."""
        return len(self._handlers.get(topic, []))

    def _require_stream(self) -> MessageStream:
        if not self._started:
            raise StateError("BrokerEventBus is not started; call await start() first")
        return self._stream

    async def _read_loop(self) -> None:
        while True:
            try:
                line = await self._stream.readline()
            except asyncio.CancelledError:
                raise
            except (OSError, ValueError):
                break
            if not line:
                break
            try:
                data = json.loads(line.decode("utf-8").strip())
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if data.get("type") != "message":
                continue
            try:
                message = EventMessage.from_dict(data["message"])
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("dropping malformed broker event: %s", exc)
                continue
            handlers = list(self._handlers.get(message.topic, []))
            for subscription in handlers:
                try:
                    await subscription.handler(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "broker event handler failed for topic %s", message.topic
                    )
        # The broker closed the connection (or the stream failed): the bus is
        # no longer usable until start() is called again.
        self._started = False
