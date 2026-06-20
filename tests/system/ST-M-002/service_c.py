import asyncio
import logging
import struct
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage
from someip.header import SOMEIPHeader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-002-ServiceC")

def multiply_handler(header: SOMEIPHeader, addr):
    """Service C: multiply(x, y) -> x * y"""
    if len(header.payload) != 8:
        logger.error("Invalid payload length")
        return None
    
    x, y = struct.unpack("!II", header.payload)
    logger.info(f"Received request multiply({x}, {y})")
    
    result = x * y
    logger.info(f"Returning result: {result}")
    return struct.pack("!I", result)

async def main():
    # Service C: ID 0x3000, Instance 0x0001, Port 33000
    mappings = {
        "service_c.dummy": SomeIPTopicMapping(
            service_id=0x3000,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=33000)
    await bus.start()
    
    # Trigger service creation
    await bus.publish(EventMessage(topic="service_c.dummy", payload="init"))
    
    # Register method
    service_key = (0x3000, 0x0001)
    publisher = bus._publishers.get(service_key)
    
    if publisher and publisher._service:
        publisher._service.register_method(0x0001, multiply_handler)
        logger.info("Service C ready - Method 0x0001 (multiply) registered on port 33000")
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
