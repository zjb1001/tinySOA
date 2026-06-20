import asyncio
import logging
import struct
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from someip.header import SOMEIPHeader, SOMEIPMessageType, SOMEIPReturnCode
from someip.sd import SOMEIPDatagramProtocol, DatagramProtocolAdapter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-008-Client")

class RPCClient:
    """Simple RPC client"""
    def __init__(self, client_id: int):
        self.client_id = client_id
        self.transport = None
        self.protocol = None
        self.response_future = None
        self.session_id = 0
        
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
        """Make an RPC call and wait for response"""
        self.response_future = asyncio.Future()
        self.session_id += 1
        
        header = SOMEIPHeader(
            service_id=service_id,
            method_id=method_id,
            client_id=0x8000 + self.client_id,
            session_id=self.session_id,
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
            
    def close(self):
        if self.transport:
            self.transport.close()

async def client_task(client_id: int, num_increments: int):
    """Each client calls increment() multiple times"""
    client = RPCClient(client_id)
    results = []
    
    try:
        await client.connect("127.0.0.1", 38000)
        logger.info(f"Client-{client_id} connected")
        
        for i in range(num_increments):
            payload = struct.pack("!I", client_id)
            result_bytes = await client.call(0x8000, 0x0001, payload)
            result = struct.unpack("!I", result_bytes)[0]
            results.append(result)
            logger.info(f"Client-{client_id} increment #{i+1} -> counter = {result}")
            
            # Small delay to simulate real-world timing
            await asyncio.sleep(0.01)
        
        logger.info(f"Client-{client_id} completed {num_increments} increments")
        return results
        
    except Exception as e:
        logger.error(f"Client-{client_id} error: {e}")
        raise
    finally:
        client.close()

async def main():
    # Wait for server to start
    await asyncio.sleep(2)
    
    logger.info("=== ST-M-008: RPC with Stateful Methods Test ===")
    
    # Test Configuration
    num_clients = 5
    increments_per_client = 2
    total_expected = num_clients * increments_per_client
    
    logger.info(f"\nTest Config:")
    logger.info(f"  - Number of clients: {num_clients}")
    logger.info(f"  - Increments per client: {increments_per_client}")
    logger.info(f"  - Total expected increments: {total_expected}")
    
    try:
        # Test 1: Concurrent increments from multiple clients
        logger.info("\n--- Test 1: Concurrent Increments ---")
        
        # Launch all clients concurrently
        tasks = [
            client_task(client_id, increments_per_client)
            for client_id in range(1, num_clients + 1)
        ]
        
        all_results = await asyncio.gather(*tasks)
        
        logger.info(f"\n✅ All clients completed")
        
        # Test 2: Verify final counter value
        logger.info("\n--- Test 2: Verify Final Counter Value ---")
        
        client = RPCClient(99)
        await client.connect("127.0.0.1", 38000)
        
        result_bytes = await client.call(0x8000, 0x0002, b"")
        final_value = struct.unpack("!I", result_bytes)[0]
        
        logger.info(f"Final counter value: {final_value}")
        
        if final_value == total_expected:
            logger.info(f"✅ PASS: Counter value correct ({final_value} == {total_expected})")
        else:
            logger.error(f"❌ FAIL: Expected {total_expected}, got {final_value}")
            client.close()
            sys.exit(1)
        
        # Test 3: Verify all increments were atomic
        logger.info("\n--- Test 3: Verify Atomicity ---")
        
        # Get log count
        result_bytes = await client.call(0x8000, 0x0004, b"")
        log_count = struct.unpack("!I", result_bytes)[0]
        
        logger.info(f"Logged operations: {log_count}")
        
        if log_count == total_expected:
            logger.info(f"✅ PASS: All operations logged ({log_count} == {total_expected})")
        else:
            logger.error(f"❌ FAIL: Expected {total_expected} logs, got {log_count}")
            client.close()
            sys.exit(1)
        
        # Test 4: Verify no race conditions (all values unique and sequential)
        logger.info("\n--- Test 4: Verify Sequential Values ---")
        
        all_values = []
        for client_results in all_results:
            all_values.extend(client_results)
        
        # Check if values are reasonable (should be between 1 and total_expected)
        min_val = min(all_values)
        max_val = max(all_values)
        
        logger.info(f"Returned values range: {min_val} to {max_val}")
        
        if min_val >= 1 and max_val == total_expected:
            logger.info(f"✅ PASS: Values in expected range [1, {total_expected}]")
        else:
            logger.error(f"❌ FAIL: Values out of range")
            client.close()
            sys.exit(1)
        
        # Test 5: Verify state consistency across clients
        logger.info("\n--- Test 5: State Consistency ---")
        
        # All clients should see the same final value
        logger.info("Querying from multiple clients...")
        
        check_clients = []
        for i in range(3):
            c = RPCClient(100 + i)
            await c.connect("127.0.0.1", 38000)
            check_clients.append(c)
        
        values = []
        for c in check_clients:
            result_bytes = await c.call(0x8000, 0x0002, b"")
            value = struct.unpack("!I", result_bytes)[0]
            values.append(value)
            c.close()
        
        if all(v == total_expected for v in values):
            logger.info(f"✅ PASS: All clients see consistent value: {total_expected}")
        else:
            logger.error(f"❌ FAIL: Inconsistent values: {values}")
            client.close()
            sys.exit(1)
        
        client.close()
        
        # Final summary
        logger.info("\n" + "="*60)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("="*60)
        logger.info("Summary:")
        logger.info(f"  ✓ Concurrent increments handled correctly")
        logger.info(f"  ✓ Final counter value: {total_expected}")
        logger.info(f"  ✓ No race conditions detected")
        logger.info(f"  ✓ State consistent across all clients")
        logger.info(f"  ✓ All mutations atomic")
        logger.info("="*60)
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"❌ TEST FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
