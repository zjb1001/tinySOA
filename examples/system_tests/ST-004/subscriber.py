"""ST-004 subscriber: service-restart resilience — subscriber survives publisher restart.

Verifies that the subscriber maintains its subscription across a publisher restart
and receives messages from the re-started publisher without re-subscribing.
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

logger = configure_logging("ST-004-SUB")


async def main() -> None:
    topic_a = "test.topic.a"
    mappings = {
        topic_a: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    install_quiet_exception_handler(logger)

    bus = SomeIPEventBus(
        mappings=mappings, local_ip="127.0.0.31", publisher_port=34010,
    )

    await bus.start()
    logger.info("\n" + "=" * 70)
    logger.info("[SUBSCRIBER READY] Bus started on 127.0.0.31")
    logger.info("[SD DISCOVERY] Registered for Service=0x1234, Instance=0x0001")
    logger.info("=" * 70 + "\n")

    received_events: list[dict] = []

    async def handler(msg: EventMessage) -> None:
        logger.info("\n" + "=" * 70)
        logger.info("[MESSAGE RECEIVED] %s: %s", msg.topic, msg.payload.get("data"))
        logger.info("=" * 70 + "\n")
        received_events.append(msg.payload)

    bus.subscribe(topic_a, handler)
    logger.info("[WAITING] for publisher to appear and send messages...")

    try:
        start_time = asyncio.get_event_loop().time()
        while len(received_events) < 2:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > 30.0:
                logger.error("Timeout waiting for messages")
                await bus.stop()
                sys.exit(1)
            await asyncio.sleep(0.1)

        logger.info("\n" + "=" * 70)
        logger.info(
            "[RESILIENCE TEST] Received %d messages after service restart",
            len(received_events),
        )
        logger.info("=" * 70 + "\n")
    except Exception as e:
        logger.error("Error during message reception: %s", e)
        await bus.stop()
        sys.exit(1)

    await bus.stop()
    logger.info("Subscriber bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
