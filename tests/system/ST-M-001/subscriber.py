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
logger = logging.getLogger("ST-M-001-Sub")

class ClientProtocol(SOMEIPDatagramProtocol):
    def __init__(self):
        super().__init__()
        self.response_future = asyncio.Future()

    def message_received(self, someip_message: SOMEIPHeader, addr, multicast: bool) -> None:
        if someip_message.message_type == SOMEIPMessageType.RESPONSE:
            if someip_message.return_code == SOMEIPReturnCode.E_OK:
                logger.info(f"Received response: {someip_message.payload}")
                if not self.response_future.done():
                    self.response_future.set_result(someip_message.payload)
            else:
                logger.error(f"Received error response: {someip_message.return_code}")
                if not self.response_future.done():
                    self.response_future.set_exception(RuntimeError(f"Error: {someip_message.return_code}"))

async def main():
    # Connect to Publisher
    # Publisher is at 127.0.0.1:31000 (based on publisher.py)
    # Wait a bit for publisher to start
    await asyncio.sleep(2)
    
    logger.info("Connecting to publisher...")
    
    prot = ClientProtocol()
    loop = asyncio.get_running_loop()
    
    # Create unicast endpoint
    transport, _ = await loop.create_datagram_endpoint(
        lambda: DatagramProtocolAdapter(prot, is_multicast=False),
        remote_addr=("127.0.0.1", 31000)
    )
    prot.transport = transport
    
    # Send Request
    # Service ID: 0x1234, Method ID: 0x0001
    payload = struct.pack("!II", 3, 5)
    header = SOMEIPHeader(
        service_id=0x1234,
        method_id=0x0001,
        client_id=0x1111,
        session_id=0x0001,
        interface_version=1,
        message_type=SOMEIPMessageType.REQUEST,
        payload=payload
    )
    
    logger.info("Sending request add(3, 5)")
    prot.send(header.build())
    
    # Wait for response
    try:
        result_bytes = await asyncio.wait_for(prot.response_future, timeout=5.0)
        result = struct.unpack("!I", result_bytes)[0]
        logger.info(f"Result: {result}")
        
        if result == 8:
            logger.info("TEST PASSED")
            sys.exit(0)
        else:
            logger.error(f"TEST FAILED: Expected 8, got {result}")
            sys.exit(1)
            
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for response")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    finally:
        transport.close()

if __name__ == "__main__":
    asyncio.run(main())
