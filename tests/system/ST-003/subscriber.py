"""ST-003 subscriber: early subscriber (joins before publisher, waits for SD Offer).

Verifies the non-centralized discovery scenario where a subscriber starts first
and waits for a late publisher to announce its service via SD.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import sys

# Make _common importable whether run as a bare script from this dir or via -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> system_tests/
from _common import configure_logging, install_quiet_exception_handler, setup_path  # noqa: E402
setup_path()  # -> adds tinysoa/src + pysomeip/src

from tinysoa.eventbus.message import EventMessage  # noqa: E402
from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping  # noqa: E402

logger = configure_logging("ST-003-SUB")


async def main() -> None:
    topic_a = "test.topic.a"
    mappings = {
        topic_a: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    install_quiet_exception_handler(logger)

    # Subscriber on its own loopback IP/port to simulate a separate ECU.
    bus = SomeIPEventBus(
        mappings=mappings, local_ip="127.0.0.21", publisher_port=33010,
    )

    await bus.start()
    logger.info("Subscriber bus started (BEFORE publisher)")

    received_event = asyncio.Event()
    received_payload: dict | None = None
    test_marker = "sub-first-test"

    async def handler(msg: EventMessage) -> None:
        nonlocal received_payload
        if msg.payload.get("data") != test_marker:
            logger.info("Ignoring non-test payload on %s: %s", msg.topic, msg.payload)
            return
        logger.info("\n" + "=" * 70)
        logger.info("[SD SUCCESS] Publisher discovered and subscribed!")
        logger.info("[MESSAGE RECEIVED] on %s: %s", msg.topic, msg.payload)
        logger.info("=" * 70 + "\n")
        received_payload = msg.payload
        received_event.set()

    # Subscribe BEFORE publisher starts (key difference from ST-002).
    bus.subscribe(topic_a, handler)
    logger.info("\n" + "=" * 70)
    logger.info("[LOCAL SERVICE TABLE] Subscriber registered for topic: %s", topic_a)
    logger.info("[SD DISCOVERY] Will send SD Find on multicast (224.224.224.245:30490)")
    logger.info("[SD DISCOVERY] Looking for Service=0x1234, Instance=0x0001, Eventgroup=0x0001")
    logger.info("[WAITING] Publisher to appear and send SD Offer...")
    logger.info("=" * 70 + "\n")

    try:
        await asyncio.wait_for(received_event.wait(), timeout=25.0)
        logger.info("Message received successfully")
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for message from late-starting publisher")
        await bus.stop()
        sys.exit(1)

    if received_payload and received_payload.get("data") == test_marker:
        logger.info("Payload verification PASSED (sub-first scenario)")
    else:
        logger.error("Payload verification FAILED. Got: %s", received_payload)
        await bus.stop()
        sys.exit(1)

    await bus.stop()
    logger.info("Subscriber bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
