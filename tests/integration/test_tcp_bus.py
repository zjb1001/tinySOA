"""Tests for TCPEventBusServer and TCPEventBusClient — the TCP protocol stack."""
from __future__ import annotations

import platform

import time

import pytest

from tinysoa.eventbus import TCPEventBusClient, TCPEventBusServer
from tinysoa.eventbus.message import EventMessage

from tests.conftest import port_free

_WSL2 = "microsoft" in platform.uname().release.lower()


# ------------------------------------------------------------------ server


class TestTCPServerLifecycle:
    def test_server_starts_and_stops_cleanly(self) -> None:
        srv = TCPEventBusServer(host="127.0.0.1", port=18766)
        if not port_free("127.0.0.1", 18766):
            pytest.skip("port 18766 in use")
        srv.start()
        assert srv._server_sock is not None
        srv.stop()
        assert srv._server_sock is None

    def test_server_stop_is_idempotent(self) -> None:
        srv = TCPEventBusServer(host="127.0.0.1", port=18767)
        if not port_free("127.0.0.1", 18767):
            pytest.skip("port 18767 in use")
        srv.start()
        srv.stop()
        srv.stop()  # must not raise


# ------------------------------------------------------------------ client


class TestTCPClientLifecycle:
    def test_client_connects_and_closes(self) -> None:
        srv = TCPEventBusServer(host="127.0.0.1", port=18768)
        if not port_free("127.0.0.1", 18768):
            pytest.skip("port 18768 in use")
        srv.start()
        try:
            client = TCPEventBusClient(host="127.0.0.1", port=18768)
            client.close()
        finally:
            srv.stop()

    def test_client_close_is_idempotent(self) -> None:
        srv = TCPEventBusServer(host="127.0.0.1", port=18769)
        if not port_free("127.0.0.1", 18769):
            pytest.skip("port 18769 in use")
        srv.start()
        try:
            client = TCPEventBusClient(host="127.0.0.1", port=18769)
            client.close()
            client.close()  # must not raise
        finally:
            srv.stop()


# ------------------------------------------------------------------ pub/sub


@pytest.mark.slow
@pytest.mark.skipif(_WSL2, reason="subprocess coordination unreliable on WSL2")
class TestTCPPubSubDelivery:
    def test_publish_subscribe_delivers_message(self) -> None:
        port = 18770
        host = "127.0.0.1"
        if not port_free(host, port):
            pytest.skip(f"port {port} in use")

        srv = TCPEventBusServer(host=host, port=port)
        srv.start()
        try:
            client1 = TCPEventBusClient(host=host, port=port)
            client2 = TCPEventBusClient(host=host, port=port)
            try:
                received: list[EventMessage] = []
                sub = client2.subscribe("test.tcp", lambda m: received.append(m))

                time.sleep(0.2)  # let subscription propagate
                msg = EventMessage(topic="test.tcp", payload={"v": 1})
                client1.publish(msg)

                time.sleep(0.5)  # let delivery propagate
                assert len(received) == 1
                assert received[0].topic == "test.tcp"
                assert received[0].payload == {"v": 1}

                client2.unsubscribe(sub)
            finally:
                client1.close()
                client2.close()
        finally:
            srv.stop()
