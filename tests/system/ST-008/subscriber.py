import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def install_quiet_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Suppress known benign shutdown errors from someip SD stack."""
    default_handler = loop.get_exception_handler() or loop.default_exception_handler

    def handler(loop_ref, ctx):
        exc = ctx.get("exception")
        if isinstance(exc, RuntimeError) and "task already stopped" in str(exc):
            return
        if isinstance(exc, AttributeError) and ("sendto" in str(exc) or "call_exception_handler" in str(exc)):
            return
        default_handler(ctx)

    loop.set_exception_handler(handler)

async def main():
    subscriber_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    logger = logging.getLogger(f"ST-008-Sub-{subscriber_id}")
    
    logger.info(f"=== ST-008 Subscriber {subscriber_id} Process ===")
    logger.info(f"Process ID: {os.getpid()}")
    
    # Define topic mapping (same as publisher)
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
    
    # Initialize Bus with different base port for each subscriber
    # Publisher uses 31000, Subscribers use 32000+ with 10-port spacing
    # is_publisher=False means this process will only subscribe, not announce
    subscriber_port = 32000 + (subscriber_id * 10)
    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=subscriber_port, is_publisher=False)
    
    await bus.start()
    logger.info(f"EventBus started on port {subscriber_port}")
    
    # Track received messages
    received_messages = []
    
    async def handler(msg: EventMessage):
        received_messages.append(msg.payload)
        logger.info(f"Received message #{msg.payload.get('message_id')} from PID {msg.payload.get('publisher_pid')}")
    
    # Subscribe to topic
    bus.subscribe(topic, handler)
    logger.info(f"Subscribed to {topic}")
    
    # Keep running and receiving messages
    try:
        # Run for 15 seconds to receive multiple messages
        await asyncio.sleep(15.0)
        
        logger.info(f"Subscriber {subscriber_id} received {len(received_messages)} messages")
        
        if len(received_messages) >= 3:
            logger.info(f"✅ Subscriber {subscriber_id} SUCCESS: Received enough messages")
        else:
            logger.warning(f"⚠️  Subscriber {subscriber_id} WARNING: Only received {len(received_messages)} messages")
        
    except asyncio.CancelledError:
        logger.info(f"Subscriber {subscriber_id} shutting down...")
    finally:
        await bus.stop()
        logger.info(f"Subscriber {subscriber_id} stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
