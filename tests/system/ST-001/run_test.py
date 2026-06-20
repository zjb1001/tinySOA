"""ST-001: Real Loopback Communication (SOME/IP in-process pub/sub).

Verifies that a message published on one topic is received by a subscriber on
the same ``SomeIPEventBus`` instance through the SOME/IP stack on loopback.

Run:
    python tests/system_tests/ST-001/run_test.py   # from repo root; _common adds paths
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Make _common importable whether run as a bare script from this dir or via -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> system_tests/
from _common import configure_logging, install_quiet_exception_handler, setup_path  # noqa: E402
setup_path()  # -> adds tinysoa/src + pysomeip/src

from tinysoa.eventbus.message import EventMessage  # noqa: E402
from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping  # noqa: E402

logger = configure_logging("ST-001")

#: Topic used exclusively by this test.
TEST_TOPIC = "test.topic.a"


async def run_test() -> None:
    """Run the ST-001 loopback pub/sub verification."""
    logger.info("Starting ST-001: Real Loopback Communication")
    install_quiet_exception_handler(logger)

    mappings = {
        TEST_TOPIC: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    bus = SomeIPEventBus(mappings=mappings, local_ip="127.0.0.1", publisher_port=31000)
    await bus.start()
    logger.info("Bus started")

    received_event = asyncio.Event()
    received_payload: dict | None = None

    async def handler(msg: EventMessage) -> None:
        nonlocal received_payload
        logger.info("Received message on %s: %s", msg.topic, msg.payload)
        received_payload = msg.payload
        received_event.set()

    # subscribe() has a built-in ~5s staggered delay before SD subscription.
    bus.subscribe(TEST_TOPIC, handler)
    logger.info("Subscribed to %s (waiting for internal SD delay...)", TEST_TOPIC)

    payload: dict = {"data": "hello world", "ts": datetime.now().isoformat()}
    await bus.publish(EventMessage(topic=TEST_TOPIC, payload=payload))
    logger.info("Published to %s", TEST_TOPIC)

    timeout = 10.0
    logger.info("Waiting up to %.0fs for message...", timeout)
    try:
        await asyncio.wait_for(received_event.wait(), timeout=timeout)
        logger.info("Message received successfully")
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for message")
        await bus.stop()
        sys.exit(1)

    if received_payload == payload:
        logger.info("Payload verification PASSED")
    else:
        logger.error(
            "Payload verification FAILED. Expected %s, got %s", payload, received_payload,
        )
        await bus.stop()
        sys.exit(1)

    await bus.stop()
    logger.info("Bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        pass
