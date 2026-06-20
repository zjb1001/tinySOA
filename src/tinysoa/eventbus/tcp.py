from __future__ import annotations

import json
import socket
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from uuid import uuid4, UUID

from .message import EventMessage
from .bus import EventBus, Subscription, EventHandler


# Simple newline-delimited JSON protocol
# Client -> Server messages:
# {"action":"subscribe","topic":"foo"}
# {"action":"unsubscribe","topic":"foo"}
# {"action":"publish","message":{EventMessage}}
#
# Server -> Client messages:
# {"type":"subscribed","topic":"foo"}
# {"type":"unsubscribed","topic":"foo"}
# {"type":"message","message":{EventMessage}}


class TCPEventBusServer:
    """A minimal TCP event bus server supporting multiple clients and topics.

    This is intended for development/demo use. It is not hardened for
    production (no auth, backpressure, or persistence).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._server_sock: Optional[socket.socket] = None
        self._clients: List[socket.socket] = []
        self._topic_clients: Dict[str, List[socket.socket]] = {}
        self._lock = threading.Lock()
        self._accept_thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()

    def start(self) -> None:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(100)
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def stop(self) -> None:
        self._stopped.set()
        with self._lock:
            for c in list(self._clients):
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
            self._topic_clients.clear()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

    def _accept_loop(self) -> None:
        assert self._server_sock is not None
        while not self._stopped.is_set():
            try:
                self._server_sock.settimeout(0.5)
                conn, _addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._clients.append(conn)
            t = threading.Thread(target=self._client_loop, args=(conn,), daemon=True)
            t.start()

    def _client_loop(self, conn: socket.socket) -> None:
        f = conn.makefile(mode="rwb")
        try:
            while not self._stopped.is_set():
                line = f.readline()
                if not line:
                    break
                try:
                    data = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue
                action = data.get("action")
                if action == "subscribe":
                    topic = data.get("topic")
                    if not topic:
                        continue
                    with self._lock:
                        self._topic_clients.setdefault(topic, []).append(conn)
                    self._send_json(f, {"type": "subscribed", "topic": topic})
                elif action == "unsubscribe":
                    topic = data.get("topic")
                    if not topic:
                        continue
                    with self._lock:
                        lst = self._topic_clients.get(topic, [])
                        self._topic_clients[topic] = [c for c in lst if c is not conn]
                        if not self._topic_clients[topic]:
                            del self._topic_clients[topic]
                    self._send_json(f, {"type": "unsubscribed", "topic": topic})
                elif action == "publish":
                    msg_dict = data.get("message")
                    if not msg_dict:
                        continue
                    # Fan-out to all clients subscribed to the topic
                    topic = msg_dict.get("topic")
                    out = json.dumps({"type": "message", "message": msg_dict}).encode("utf-8") + b"\n"
                    targets: List[socket.socket]
                    with self._lock:
                        targets = list(self._topic_clients.get(topic, []))
                    for client in targets:
                        try:
                            client.sendall(out)
                        except Exception:
                            # Drop broken client from all topics
                            self._remove_client(client)
                else:
                    # ignore unknown
                    pass
        finally:
            try:
                f.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._remove_client(conn)

    def _remove_client(self, conn: socket.socket) -> None:
        if conn in self._clients:
            self._clients.remove(conn)
        for topic in list(self._topic_clients.keys()):
            lst = self._topic_clients[topic]
            self._topic_clients[topic] = [c for c in lst if c is not conn]
            if not self._topic_clients[topic]:
                del self._topic_clients[topic]

    @staticmethod
    def _send_json(f, obj) -> None:
        try:
            f.write(json.dumps(obj).encode("utf-8") + b"\n")
            f.flush()
        except Exception:
            pass


class TCPEventBusClient(EventBus):
    """TCP client implementing the EventBus API against TCPEventBusServer."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._sock = socket.create_connection((self.host, self.port))
        self._file_r = self._sock.makefile(mode="rb")
        self._file_w = self._sock.makefile(mode="wb")
        self._handlers: Dict[str, List[Subscription]] = {}
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def close(self) -> None:
        try:
            self._file_r.close()
        except Exception:
            pass
        try:
            self._file_w.close()
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass

    def publish(self, message: EventMessage) -> None:
        obj = {"action": "publish", "message": message.to_dict()}
        with self._lock:
            self._file_w.write(json.dumps(obj).encode("utf-8") + b"\n")
            self._file_w.flush()

    def subscribe(self, topic: str, handler: EventHandler) -> Subscription:
        sub = Subscription(id=uuid4(), topic=topic, handler=handler)
        obj = {"action": "subscribe", "topic": topic}
        with self._lock:
            self._file_w.write(json.dumps(obj).encode("utf-8") + b"\n")
            self._file_w.flush()
            self._handlers.setdefault(topic, []).append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        obj = {"action": "unsubscribe", "topic": subscription.topic}
        with self._lock:
            try:
                self._file_w.write(json.dumps(obj).encode("utf-8") + b"\n")
                self._file_w.flush()
            except Exception:
                pass
            lst = self._handlers.get(subscription.topic, [])
            self._handlers[subscription.topic] = [s for s in lst if s.id != subscription.id]
            if not self._handlers[subscription.topic]:
                del self._handlers[subscription.topic]

    def get_subscribers_count(self, topic: str) -> int:
        with self._lock:
            return len(self._handlers.get(topic, []))

    def _read_loop(self) -> None:
        f = self._file_r
        while True:
            try:
                line = f.readline()
                if not line:
                    break
                data = json.loads(line.decode("utf-8").strip())
            except Exception:
                break
            typ = data.get("type")
            if typ == "message":
                msg = EventMessage.from_dict(data["message"])
                # snapshot handlers to call without holding lock
                with self._lock:
                    subs = list(self._handlers.get(msg.topic, []))
                for sub in subs:
                    try:
                        sub.handler(msg)
                    except Exception:
                        # ignore handler exceptions to keep stream alive
                        pass
            else:
                # Other control messages ignored for now
                pass
