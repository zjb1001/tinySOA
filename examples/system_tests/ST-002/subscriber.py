import asyncio
import logging
import os
import sys
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-002-SUB")


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
    topic_a = "test.topic.a"
    mappings = {
        topic_a: SomeIPTopicMapping(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x0001,
        )
    }

    loop = asyncio.get_running_loop()
    install_quiet_exception_handler(loop)

    # Subscriber uses a different loopback IP/port base to simulate a separate ECU/process.
    bus = SomeIPEventBus(
        mappings=mappings,
        local_ip="127.0.0.12",
        publisher_port=32020,
    )

    await bus.start()
    logger.info("Subscriber bus started")

    received_event = asyncio.Event()
    received_payload = None
    validation_marker = "late-sub"

    async def handler(msg: EventMessage):
        nonlocal received_payload
        if msg.payload.get("data") != validation_marker:
            logger.info(f"Ignoring non-validation payload on {msg.topic}: {msg.payload}")
            return
        logger.info(f"Received validation message on {msg.topic}: {msg.payload}")
        received_payload = msg.payload
        received_event.set()

    bus.subscribe(topic_a, handler)
    logger.info("Subscribed (will wait for internal SD delay before activating)")

    try:
        await asyncio.wait_for(received_event.wait(), timeout=20.0)
        logger.info("Message received successfully")
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for validation message")
        await bus.stop()
        sys.exit(1)

    # Verification
    if received_payload and received_payload.get("data") == validation_marker:
        logger.info("Payload verification PASSED (late subscriber scenario)")
    else:
        logger.error(f"Payload verification FAILED. Got: {received_payload}")
        await bus.stop()
        sys.exit(1)

    await bus.stop()
    logger.info("Subscriber bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
