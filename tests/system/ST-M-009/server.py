import asyncio
import logging
import struct
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage
from someip.header import SOMEIPHeader, SOMEIPMessageType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-009-Server")

# Shared state to track method executions
execution_log = []

def log_event_handler(header: SOMEIPHeader, addr):
    """Fire-and-forget handler: logs events without returning response"""
    global execution_log
    
    # Check message type - should be REQUEST_NO_RETURN
    if header.message_type != SOMEIPMessageType.REQUEST_NO_RETURN:
        logger.warning(f"Expected REQUEST_NO_RETURN, got {header.message_type}")
    
    if len(header.payload) < 4:
        logger.error("Invalid payload length")
        return None
    
    # Parse event_id
    event_id = struct.unpack("!I", header.payload[:4])[0]
    timestamp = datetime.now().isoformat()
    
    # Simulate some processing time
    import time
    time.sleep(0.1)
    
    execution_log.append({
        'event_id': event_id,
        'timestamp': timestamp,
        'addr': str(addr)
    })
    
    logger.info(f"[Fire-and-Forget] Logged event #{event_id} from {addr}")
    
    # Return None - no response for fire-and-forget
    return None

def get_log_count_handler(header: SOMEIPHeader, addr):
    """Regular RPC handler: returns count of logged events"""
    global execution_log
    
    count = len(execution_log)
    logger.info(f"[RPC] Returning log count: {count}")
    
    return struct.pack("!I", count)

async def main():
    # Server: ID 0x9000, Instance 0x0001, Port 39000
    mappings = {
        "server.dummy": SomeIPTopicMapping(
            service_id=0x9000,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=39000)
    await bus.start()
    
    # Trigger service creation
    await bus.publish(EventMessage(topic="server.dummy", payload="init"))
    
    # Register methods
    service_key = (0x9000, 0x0001)
    publisher = bus._publishers.get(service_key)
    
    if publisher and publisher._service:
        # Method 0x0001: log_event (fire-and-forget)
        publisher._service.register_method(0x0001, log_event_handler)
        # Method 0x0002: get_log_count (regular RPC)
        publisher._service.register_method(0x0002, get_log_count_handler)
        logger.info("Server ready:")
        logger.info("  - Method 0x0001 (log_event) - Fire-and-Forget")
        logger.info("  - Method 0x0002 (get_log_count) - Regular RPC")
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
