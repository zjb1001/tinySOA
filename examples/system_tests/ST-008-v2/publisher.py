#!/usr/bin/env python3
"""
ST-008 Multi-Process Deployment Scenario (v2)
============================================
Uses Method RPC instead of EventGroup Pub/Sub to verify multi-process communication.
This avoids the complex SD announcer issues with Pub/Sub in multi-process scenarios.

Publisher: Provides a simple_add(a, b) method
Subscribers: Call this method repeatedly from different processes
"""

import asyncio
import logging
import struct
import sys
import os
import time
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage
from someip.header import SOMEIPHeader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ST-008-Pub-v2")


def install_quiet_exception_handler(loop):
    """Suppress noisy task exception logs."""
    def handle_exception(args):
        pass
    loop.set_exception_handler(handle_exception)


def simple_add_handler(header: SOMEIPHeader, addr):
    """RPC handler: adds two integers"""
    if len(header.payload) != 8:
        logger.error(f"Invalid payload length: {len(header.payload)}")
        return None
    
    try:
        a, b = struct.unpack("!II", header.payload)
        result = a + b
        logger.info(f"RPC simple_add({a}, {b}) = {result} from {addr}")
        return struct.pack("!I", result)
    except Exception as e:
        logger.error(f"Handler exception: {e}")
        return None


async def main():
    logger.info("=== ST-008 Publisher Process (v2) ===")
    logger.info(f"Process ID: {os.getpid()}")
    
    # Dummy mapping to create service structure
    # We'll use methods, not eventgroups
    mappings = {
        "multiprocess.add": SomeIPTopicMapping(
            service_id=0x0800,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    loop = asyncio.get_running_loop()
    install_quiet_exception_handler(loop)
    
    # Publisher mode with announcer for advertising methods
    bus = SomeIPEventBus(
        mappings=mappings,
        local_ip="127.0.0.1",
        publisher_port=31000,
        is_publisher=True
    )
    
    await bus.start()
    logger.info("EventBus started on port 31000")
    
    # Create a dummy publication to initialize the service
    await bus.publish(EventMessage(topic="multiprocess.add", payload="init"))
    logger.info("Service structure initialized")
    
    # Get publisher and register method
    service_key = (0x0800, 0x0001)
    publisher = bus._publishers.get(service_key)
    
    if publisher and publisher._service:
        publisher._service.register_method(0x0001, simple_add_handler)
        logger.info("Registered RPC method 0x0001 (simple_add)")
    else:
        logger.error("Service not started correctly")
        await bus.stop()
        sys.exit(1)

    logger.info("Publisher ready. Waiting for RPC calls...")
    
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await bus.stop()
        logger.info("Publisher stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
