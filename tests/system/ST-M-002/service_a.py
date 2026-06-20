"""ST-M-002 Service A: RPC chain orchestrator.

Calls Service B's ``add_then_multiply(3, 5)`` via raw SOME/IP RPC (pysomeip
``SOMEIPHeader`` / ``SOMEIPDatagramProtocol``), expecting ``(3+5)*2 = 16``.

Run as its own OS process after Service B and Service C are running.

Run:
    python tests/system_tests/ST-M-002/service_a.py   # from repo root; _common adds paths
"""
from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path
from typing import Optional

# Make _common importable whether run as a bare script from this dir or via -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> system_tests/
from _common import configure_logging, setup_path  # noqa: E402
setup_path()  # -> adds tinysoa/src + pysomeip/src

from someip.header import (  # noqa: E402
    SOMEIPHeader,
    SOMEIPMessageType,
    SOMEIPReturnCode,
)
from someip.sd import SOMEIPDatagramProtocol, DatagramProtocolAdapter  # noqa: E402

logger = configure_logging("ST-M-002-ServiceA")


class RPCClient:
    """Simple RPC client for making synchronous SOME/IP calls."""

    def __init__(self) -> None:
        self.transport: Optional[object] = None
        self.protocol: Optional[object] = None
        self.response_future: Optional[asyncio.Future] = None

    async def connect(self, host: str, port: int) -> None:
        loop = asyncio.get_running_loop()

        class ClientProtocol(SOMEIPDatagramProtocol):
            def __init__(self, parent: RPCClient) -> None:
                super().__init__()
                self.parent = parent

            def message_received(
                self, someip_message: SOMEIPHeader, addr, multicast: bool
            ) -> None:
                if someip_message.message_type == SOMEIPMessageType.RESPONSE:
                    if someip_message.return_code == SOMEIPReturnCode.E_OK:
                        if (
                            self.parent.response_future
                            and not self.parent.response_future.done()
                        ):
                            self.parent.response_future.set_result(
                                someip_message.payload
                            )
                    else:
                        if (
                            self.parent.response_future
                            and not self.parent.response_future.done()
                        ):
                            self.parent.response_future.set_exception(
                                RuntimeError(f"Error: {someip_message.return_code}")
                            )

        self.protocol = ClientProtocol(self)
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: DatagramProtocolAdapter(self.protocol, is_multicast=False),
            remote_addr=(host, port),
        )
        self.protocol.transport = self.transport

    async def call(
        self,
        service_id: int,
        method_id: int,
        payload: bytes,
        timeout: float = 5.0,
    ) -> bytes:
        """Make an RPC call and wait for the response."""
        self.response_future = asyncio.Future()

        header = SOMEIPHeader(
            service_id=service_id,
            method_id=method_id,
            client_id=0x1111,
            session_id=0x0001,
            interface_version=1,
            message_type=SOMEIPMessageType.REQUEST,
            payload=payload,
        )
        self.protocol.send(header.build())

        try:
            return await asyncio.wait_for(self.response_future, timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("RPC call timeout")

    def close(self) -> None:
        if self.transport:
            self.transport.close()


async def main() -> None:
    # Allow Service B / C time to start.
    await asyncio.sleep(3)

    logger.info("Service A: Starting RPC call chain test")
    logger.info("Calling Service B: add_then_multiply(3, 5)")

    client = RPCClient()
    try:
        await client.connect("127.0.0.1", 32000)

        payload = struct.pack("!II", 3, 5)
        result_bytes = await client.call(0x2000, 0x0001, payload, timeout=10.0)
        result: int = struct.unpack("!I", result_bytes)[0]

        logger.info("Final result: %d", result)

        expected = 16
        if result == expected:
            logger.info("✅ TEST PASSED: Got expected result %d", expected)
            sys.exit(0)
        else:
            logger.error("❌ TEST FAILED: Expected %d, got %d", expected, result)
            sys.exit(1)

    except Exception as e:
        logger.error("❌ TEST FAILED with error: %s", e)
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
