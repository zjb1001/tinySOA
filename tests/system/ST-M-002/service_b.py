import asyncio
import logging
import struct
import sys
import os
import concurrent.futures

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage
from someip.header import SOMEIPHeader, SOMEIPMessageType, SOMEIPReturnCode
from someip.sd import SOMEIPDatagramProtocol, DatagramProtocolAdapter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-002-ServiceB")

class RPCClient:
    """Simple RPC client for making synchronous calls"""
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
        """Make an RPC call and wait for response"""
        self.response_future = asyncio.Future()
        
        header = SOMEIPHeader(
            service_id=service_id,
            method_id=method_id,
            client_id=0x2222,
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
            
    def close(self):
        if self.transport:
            self.transport.close()

def add_then_multiply_handler(header: SOMEIPHeader, addr):
    """Service B: add_then_multiply(a, b) -> calls C.multiply(a+b, 2)"""
    if len(header.payload) != 8:
        logger.error("Invalid payload length")
        return None
    
    a, b = struct.unpack("!II", header.payload)
    logger.info(f"Received request add_then_multiply({a}, {b})")
    
    # Calculate a + b
    sum_result = a + b
    logger.info(f"Step 1: {a} + {b} = {sum_result}")
    
    # Call Service C's multiply method in a new thread with new event loop
    def call_service_c_sync():
        async def call_service_c():
            client = RPCClient()
            try:
                await client.connect("127.0.0.1", 33000)
                logger.info(f"Step 2: Calling Service C multiply({sum_result}, 2)")
                
                payload = struct.pack("!II", sum_result, 2)
                result_bytes = await client.call(0x3000, 0x0001, payload)
                result = struct.unpack("!I", result_bytes)[0]
                
                logger.info(f"Step 3: Got result from Service C: {result}")
                return result
            finally:
                client.close()
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(call_service_c())
        finally:
            loop.close()
    
    # Execute in thread pool
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(call_service_c_sync)
            result = future.result(timeout=5.0)
            return struct.pack("!I", result)
    except Exception as e:
        logger.error(f"Error calling Service C: {e}")
        return None

async def main():
    # Service B: ID 0x2000, Instance 0x0001, Port 32000
    mappings = {
        "service_b.dummy": SomeIPTopicMapping(
            service_id=0x2000,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=32000)
    await bus.start()
    
    # Trigger service creation
    await bus.publish(EventMessage(topic="service_b.dummy", payload="init"))
    
    # Register method
    service_key = (0x2000, 0x0001)
    publisher = bus._publishers.get(service_key)
    
    if publisher and publisher._service:
        publisher._service.register_method(0x0001, add_then_multiply_handler)
        logger.info("Service B ready - Method 0x0001 (add_then_multiply) registered on port 32000")
    else:
        logger.error("Service not started correctly")
        await bus.stop()
        sys.exit(1)

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await bus.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
