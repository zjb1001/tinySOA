from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
from typing import Dict, List, Optional, Set

from tinysoa.core.errors import StateError

from .bus import EventBusBroker, EventHandler, ManagedEventBus, Subscription, Topology
from .message import EventMessage
from .stream import MessageStream

logger = logging.getLogger(__name__)


# Simple newline-delimited JSON protocol.
# Client -> Broker messages:
# {"action":"subscribe","topic":"foo"}
# {"action":"unsubscribe","topic":"foo"}
# {"action":"publish","message":{EventMessage}}
#
# Broker -> Client messages:
# {"type":"subscribed","topic":"foo"}
# {"type":"unsubscribed","topic":"foo"}
# {"type":"message","message":{EventMessage}}


class TCPEventBusBroker(EventBusBroker):
    """A minimal TCP event bus broker supporting multiple clients and topics.

    This is the central relay of the ``BROKER`` topology: publishers and
    subscribers connect to it and never talk to each other directly.  It is
    intended for development/demo use; it is not hardened for production (no
    auth, backpressure, or persistence).
    """

    topology = Topology.BROKER

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._server_sock: Optional[socket.socket] = None
        self._clients: Set[socket.socket] = set()
        self._topic_clients: Dict[str, Set[socket.socket]] = {}
        self._send_locks: Dict[socket.socket, threading.Lock] = {}
        self._lock = threading.Lock()
        self._accept_thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()

    def start(self) -> None:
        if self._server_sock is not None:
            return
        self._stopped.clear()
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(100)
        # Resolve an ephemeral port (port=0) so callers can read the real one.
        self.port = server_sock.getsockname()[1]
        self._server_sock = server_sock
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="tinysoa-tcp-broker-accept",
            daemon=True,
        )
        self._accept_thread.start()

    def stop(self) -> None:
        self._stopped.set()
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
            self._topic_clients.clear()
            self._send_locks.clear()
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        server_sock, self._server_sock = self._server_sock, None
        if server_sock is not None:
            try:
                server_sock.close()
            except OSError:
                pass
        accept_thread, self._accept_thread = self._accept_thread, None
        if (
            accept_thread is not None
            and accept_thread is not threading.current_thread()
        ):
            accept_thread.join(timeout=1.0)

    def _accept_loop(self) -> None:
        while not self._stopped.is_set():
            server_sock = self._server_sock
            if server_sock is None:
                break
            try:
                server_sock.settimeout(0.5)
                conn, _addr = server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._clients.add(conn)
                self._send_locks[conn] = threading.Lock()
            threading.Thread(
                target=self._client_loop,
                args=(conn,),
                name="tinysoa-tcp-broker-client",
                daemon=True,
            ).start()

    def _client_loop(self, conn: socket.socket) -> None:
        reader = conn.makefile(mode="rb")
        try:
            while not self._stopped.is_set():
                line = reader.readline()
                if not line:
                    break
                try:
                    data = json.loads(line.decode("utf-8").strip())
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                action = data.get("action")
                if action == "subscribe":
                    topic = data.get("topic")
                    if not topic:
                        continue
                    with self._lock:
                        self._topic_clients.setdefault(topic, set()).add(conn)
                    self._send_json(conn, {"type": "subscribed", "topic": topic})
                elif action == "unsubscribe":
                    topic = data.get("topic")
                    if not topic:
                        continue
                    with self._lock:
                        subscribers = self._topic_clients.get(topic)
                        if subscribers is not None:
                            subscribers.discard(conn)
                            if not subscribers:
                                del self._topic_clients[topic]
                    self._send_json(conn, {"type": "unsubscribed", "topic": topic})
                elif action == "publish":
                    msg_dict = data.get("message")
                    if not msg_dict:
                        continue
                    topic = msg_dict.get("topic")
                    if not topic:
                        continue
                    out = (
                        json.dumps({"type": "message", "message": msg_dict}).encode(
                            "utf-8"
                        )
                        + b"\n"
                    )
                    with self._lock:
                        targets = list(self._topic_clients.get(topic, ()))
                    for client in targets:
                        if not self._send_bytes(client, out):
                            with self._lock:
                                self._remove_client_locked(client)
                # Unknown actions are ignored for forward compatibility.
        except OSError:
            pass
        finally:
            try:
                reader.close()
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
            with self._lock:
                self._remove_client_locked(conn)

    def _remove_client_locked(self, conn: socket.socket) -> None:
        """Drop a client; caller MUST hold ``self._lock``."""
        self._clients.discard(conn)
        self._send_locks.pop(conn, None)
        for topic in list(self._topic_clients):
            subscribers = self._topic_clients[topic]
            subscribers.discard(conn)
            if not subscribers:
                del self._topic_clients[topic]

    def _send_bytes(self, conn: socket.socket, data: bytes) -> bool:
        with self._lock:
            send_lock = self._send_locks.get(conn)
        if send_lock is None:
            return False
        try:
            with send_lock:
                conn.sendall(data)
            return True
        except OSError:
            return False

    def _send_json(self, conn: socket.socket, obj: dict) -> None:
        self._send_bytes(conn, json.dumps(obj).encode("utf-8") + b"\n")


class TCPMessageStream(MessageStream):
    """Newline-delimited frames over a TCP connection.

    This class owns *only* the socket/stream.  Topic routing, subscription
    bookkeeping, and the broker wire protocol stay in :class:`TCPEventBus`.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    @property
    def is_open(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def open(self) -> None:
        if self.is_open:
            return
        await self.close()
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def close(self) -> None:
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, RuntimeError):
            pass

    def write(self, frame: bytes) -> None:
        writer = self._writer
        if writer is None or writer.is_closing():
            raise StateError("TCPMessageStream is not open")
        writer.write(frame)

    async def drain(self) -> None:
        writer = self._writer
        if writer is None or writer.is_closing():
            raise StateError("TCPMessageStream is not open")
        await writer.drain()

    async def readline(self) -> bytes:
        reader = self._reader
        if reader is None:
            return b""
        return await reader.readline()


class TCPEventBus(ManagedEventBus):
    """TCP client implementing the EventBus API against a TCP broker.

    Topology ``BROKER``: a broker (see :class:`TCPEventBusBroker`) must be
    running before :meth:`start` is called.  The client is asyncio-native:
    ``publish`` and every subscribed handler are awaited on the event loop.

    The transport is injected as a :class:`MessageStream`; TCP is the current
    implementation, not part of the bus semantics.
    """

    topology = Topology.BROKER

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._stream: MessageStream = TCPMessageStream(host, port)
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
            name=f"tinysoa-tcp-reader-{self.host}:{self.port}",
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
        """Send one event to the broker."""
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
            raise StateError("TCPEventBus is not started; call await start() first")
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
                logger.warning("dropping malformed TCP event: %s", exc)
                continue
            handlers = list(self._handlers.get(message.topic, []))
            for subscription in handlers:
                try:
                    await subscription.handler(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "TCP event handler failed for topic %s", message.topic
                    )
        # The broker closed the connection (or the stream failed): the bus is
        # no longer usable until start() is called again.
        self._started = False


# Backward-compatible aliases.  Note that ``TCPEventBusClient`` now requires
# ``await start()`` before use (it used to connect in the constructor).
TCPEventBusClient = TCPEventBus
TCPEventBusServer = TCPEventBusBroker
