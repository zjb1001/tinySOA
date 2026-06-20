import asyncio
import logging
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-008-Publisher")

def install_quiet_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Suppress known benign shutdown errors from someip SD stack."""
    default_handler = loop.get_exception_handler() or loop.default_exception_handler

    def handler(loop_ref, ctx):
        exc = ctx.get("exception")
        if isinstance(exc, RuntimeError) and "task already stopped" in str(exc):
            logger.debug("Swallowing expected RuntimeError during shutdown: %s", exc)
            return
        if isinstance(exc, AttributeError) and ("sendto" in str(exc) or "call_exception_handler" in str(exc)):
            logger.debug("Swallowing expected AttributeError during shutdown: %s", exc)
            return
        default_handler(ctx)

    loop.set_exception_handler(handler)

async def main():
    logger.info("=== ST-008 Publisher Process ===")
    logger.info(f"Process ID: {os.getpid()}")
    
    # Define topic mapping
    topic = "test.multiprocess"
    mappings = {
        topic: SomeIPTopicMapping(
            service_id=0x0800,
            instance_id=0x0001,
            eventgroup_id=0x0001
        )
    }
    
    loop = asyncio.get_running_loop()
    install_quiet_exception_handler(loop)
    
    # Initialize Bus on port 31000 for service data
    # SD discovery port 30490 is shared, service ports must differ
    # is_publisher=True means this process will announce services
    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=31000, is_publisher=True)
    
    await bus.start()
    logger.info("EventBus started on port 31000")
    
    # Give SD time to fully stabilize before publishing
    await asyncio.sleep(1)
    
    # Trigger publisher creation by publishing first message
    payload_init = {
        "message_id": 0,
        "timestamp": datetime.now().isoformat(),
        "publisher_pid": os.getpid()
    }
    msg_init = EventMessage(topic=topic, payload=payload_init)
    await bus.publish(msg_init)
    logger.info("Publisher service initialized")
    
    # Wait for subscribers to discover
    await asyncio.sleep(2)
    
    # Publish messages periodically
    message_count = 0
    
    try:
        while True:
            message_count += 1
            payload = {
                "message_id": message_count,
                "timestamp": datetime.now().isoformat(),
                "publisher_pid": os.getpid()
            }
            
            msg = EventMessage(topic=topic, payload=payload)
            await bus.publish(msg)
            
            logger.info(f"Published message #{message_count}")
            
            # Publish every 2 seconds
            await asyncio.sleep(2.0)
            
    except asyncio.CancelledError:
        logger.info("Publisher shutting down...")
        await bus.stop()
        logger.info("Publisher stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Publisher interrupted by user")
