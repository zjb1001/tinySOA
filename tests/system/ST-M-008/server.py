import asyncio
import logging
import struct
import sys
import os
import threading

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage
from someip.header import SOMEIPHeader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-M-008-Server")

# Shared state with thread-safe access
class Counter:
    """Thread-safe counter for stateful RPC methods"""
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()
        self._increment_log = []
    
    def increment(self, client_id: str) -> int:
        """Atomically increment counter and log operation"""
        with self._lock:
            self._value += 1
            new_value = self._value
            self._increment_log.append({
                'client_id': client_id,
                'value': new_value
            })
            logger.info(f"[STATEFUL] increment() by {client_id} -> counter = {new_value}")
            return new_value
    
    def get_value(self) -> int:
        """Get current counter value"""
        with self._lock:
            return self._value
    
    def reset(self) -> None:
        """Reset counter to 0"""
        with self._lock:
            self._value = 0
            self._increment_log.clear()
            logger.info("[STATEFUL] reset() -> counter = 0")
    
    def get_log(self) -> list:
        """Get increment operation log"""
        with self._lock:
            return list(self._increment_log)

# Global counter instance
counter = Counter()

def increment_handler(header: SOMEIPHeader, addr):
    """RPC handler: increment counter"""
    global counter
    
    if len(header.payload) != 4:
        logger.error("Invalid payload length")
        return None
    
    # Parse client_id from payload
    client_id = struct.unpack("!I", header.payload)[0]
    
    # Atomically increment
    new_value = counter.increment(f"Client-{client_id}")
    
    # Return new value
    return struct.pack("!I", new_value)

def get_value_handler(header: SOMEIPHeader, addr):
    """RPC handler: get current counter value"""
    global counter
    
    value = counter.get_value()
    logger.info(f"[STATEFUL] get_value() -> {value}")
    
    return struct.pack("!I", value)

def reset_handler(header: SOMEIPHeader, addr):
    """RPC handler: reset counter to 0"""
    global counter
    
    counter.reset()
    
    # Return success (0)
    return struct.pack("!I", 0)

def get_log_handler(header: SOMEIPHeader, addr):
    """RPC handler: get increment log (returns count)"""
    global counter
    
    log = counter.get_log()
    count = len(log)
    
    logger.info(f"[STATEFUL] get_log() -> {count} operations")
    
    return struct.pack("!I", count)

async def main():
    # Server: ID 0x8000, Instance 0x0001, Port 38000
    mappings = {
        "server.dummy": SomeIPTopicMapping(
            service_id=0x8000,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=38000)
    await bus.start()
    
    # Trigger service creation
    await bus.publish(EventMessage(topic="server.dummy", payload="init"))
    
    # Register methods
    service_key = (0x8000, 0x0001)
    publisher = bus._publishers.get(service_key)
    
    if publisher and publisher._service:
        # Method 0x0001: increment
        publisher._service.register_method(0x0001, increment_handler)
        # Method 0x0002: get_value
        publisher._service.register_method(0x0002, get_value_handler)
        # Method 0x0003: reset
        publisher._service.register_method(0x0003, reset_handler)
        # Method 0x0004: get_log
        publisher._service.register_method(0x0004, get_log_handler)
        logger.info("Server ready with stateful methods:")
        logger.info("  - Method 0x0001 (increment)")
        logger.info("  - Method 0x0002 (get_value)")
        logger.info("  - Method 0x0003 (reset)")
        logger.info("  - Method 0x0004 (get_log)")
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
