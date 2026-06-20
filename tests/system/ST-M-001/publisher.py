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
logger = logging.getLogger("ST-M-001-Pub")

def add_handler(header: SOMEIPHeader, addr):
    # Expecting two 32-bit integers (big endian)
    if len(header.payload) != 8:
        logger.error("Invalid payload length")
        return None
    
    a, b = struct.unpack("!II", header.payload)
    logger.info(f"Received request add({a}, {b})")
    
    result = a + b
    return struct.pack("!I", result)

async def main():
    # Define a dummy mapping to force service creation
    # Service ID: 0x1234, Instance ID: 0x0001
    mappings = {
        "dummy.topic": SomeIPTopicMapping(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    # Initialize Bus
    # We use a specific port for the publisher so the client knows where to send
    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=31000)
    
    await bus.start()
    
    # Trigger publisher creation by publishing a dummy message
    await bus.publish(EventMessage(topic="dummy.topic", payload="init"))
    
    # Access the publisher and register method
    service_key = (0x1234, 0x0001)
    publisher = bus._publishers.get(service_key)
    
    if publisher and publisher._service:
        publisher._service.register_method(0x0001, add_handler)
        logger.info("Registered method 0x0001 (add)")
    else:
        logger.error("Service not started correctly")
        await bus.stop()
        sys.exit(1)

    logger.info("Publisher ready. Waiting for requests...")

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
