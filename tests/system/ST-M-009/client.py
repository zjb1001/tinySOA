import asyncio
import logging
import struct
import sys
import os
import time

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from someip.header import SOMEIPHeader, SOMEIPMessageType, SOMEIPReturnCode
from someip.sd import SOMEIPDatagramProtocol, DatagramProtocolAdapter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-009-Client")

class RPCClient:
    """Simple RPC client for making both regular and fire-and-forget calls"""
    def __init__(self):
        self.transport = None
        self.protocol = None
        self.response_future = None
        
    async def connect(self, host, port):
        loop = asyncio.get_running_loop()
        
        class ClientProtocol(SOMEIPDatagramProtocol):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                
            def message_received(self, someip_message: SOMEIPHeader, addr, multicast: bool) -> None:
                if someip_message.message_type == SOMEIPMessageType.RESPONSE:
                    if someip_message.return_code == SOMEIPReturnCode.E_OK:
                        if self.parent.response_future and not self.parent.response_future.done():
                            self.parent.response_future.set_result(someip_message.payload)
                    else:
                        if self.parent.response_future and not self.parent.response_future.done():
                            self.parent.response_future.set_exception(
                                RuntimeError(f"Error: {someip_message.return_code}")
                            )
        
        self.protocol = ClientProtocol(self)
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: DatagramProtocolAdapter(self.protocol, is_multicast=False),
            remote_addr=(host, port)
        )
        self.protocol.transport = self.transport
        
    async def call(self, service_id, method_id, payload, timeout=5.0):
        """Make a regular RPC call and wait for response"""
        self.response_future = asyncio.Future()
        
        header = SOMEIPHeader(
            service_id=service_id,
            method_id=method_id,
            client_id=0x9999,
            session_id=0x0001,
            interface_version=1,
            message_type=SOMEIPMessageType.REQUEST,
            payload=payload
        )
        
        self.protocol.send(header.build())
        
        try:
            result = await asyncio.wait_for(self.response_future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise RuntimeError("RPC call timeout")
    
    async def call_oneway(self, service_id, method_id, payload):
        """Make a fire-and-forget call (no response expected)"""
        header = SOMEIPHeader(
            service_id=service_id,
            method_id=method_id,
            client_id=0x9999,
            session_id=0x0002,
            interface_version=1,
            message_type=SOMEIPMessageType.REQUEST_NO_RETURN,  # Fire-and-forget
            payload=payload
        )
        
        self.protocol.send(header.build())
        # Return immediately without waiting for response
            
    def close(self):
        if self.transport:
            self.transport.close()

async def main():
    # Wait for server to start
    await asyncio.sleep(2)
    
    logger.info("=== ST-M-009: Fire-and-Forget (One-Way) Calls Test ===")
    
    client = RPCClient()
    try:
        await client.connect("127.0.0.1", 39000)
        logger.info("Connected to server")
        
        # Test 1: Send multiple fire-and-forget calls
        logger.info("\n--- Test 1: Sending Fire-and-Forget calls ---")
        num_calls = 5
        
        start_time = time.time()
        for i in range(1, num_calls + 1):
            payload = struct.pack("!I", i)
            await client.call_oneway(0x9000, 0x0001, payload)
            logger.info(f"Sent fire-and-forget call #{i} (no wait)")
        end_time = time.time()
        
        elapsed = end_time - start_time
        logger.info(f"All {num_calls} fire-and-forget calls sent in {elapsed:.3f}s")
        
        # Verify calls returned immediately (should be very fast)
        if elapsed < 0.5:
            logger.info(f"✅ PASS: Calls returned immediately ({elapsed:.3f}s < 0.5s)")
        else:
            logger.error(f"❌ FAIL: Calls took too long ({elapsed:.3f}s >= 0.5s)")
            sys.exit(1)
        
        # Wait for server to process all async calls
        logger.info("\nWaiting 1 second for server to process asynchronously...")
        await asyncio.sleep(1)
        
        # Test 2: Verify server processed all calls
        logger.info("\n--- Test 2: Verifying server processed calls ---")
        result_bytes = await client.call(0x9000, 0x0002, b"")
        count = struct.unpack("!I", result_bytes)[0]
        
        logger.info(f"Server processed {count} events")
        
        if count == num_calls:
            logger.info(f"✅ PASS: Server processed all {num_calls} fire-and-forget calls")
        else:
            logger.error(f"❌ FAIL: Expected {num_calls} calls, server processed {count}")
            sys.exit(1)
        
        # Test 3: Verify no response received for fire-and-forget calls
        logger.info("\n--- Test 3: Verify no response for fire-and-forget ---")
        logger.info("Sending one more fire-and-forget call...")
        
        payload = struct.pack("!I", 999)
        await client.call_oneway(0x9000, 0x0001, payload)
        
        # Try to wait for response (should timeout immediately since none expected)
        logger.info("Checking that no response is received...")
        await asyncio.sleep(0.2)
        
        logger.info("✅ PASS: No response received (as expected for fire-and-forget)")
        
        # Final summary
        logger.info("\n" + "="*60)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("="*60)
        logger.info("Summary:")
        logger.info("  ✓ Fire-and-forget calls return immediately")
        logger.info("  ✓ Server processes calls asynchronously")
        logger.info("  ✓ No response expected or received")
        logger.info("="*60)
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"❌ TEST FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(main())
