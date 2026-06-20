"""ST-003 publisher: late publisher (subscriber starts first then publisher joins).

Verifies the non-centralized SOME/IP SD scenario where a subscriber sends SD Find
before the publisher is running; the publisher later announces via SD Offer and
the subscriber discovers and receives.
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

logger = configure_logging("ST-003-PUB")


async def main() -> None:
    topic_a = "test.topic.a"
    mappings = {
        topic_a: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    install_quiet_exception_handler(logger)

    # Publisher runs on a different loopback IP/port base to simulate a
    # separate ECU/process.  It starts AFTER the subscriber has already sent SD Find.
    bus = SomeIPEventBus(
        mappings=mappings, local_ip="127.0.0.22", publisher_port=33020,
    )

    await bus.start()
    logger.info("\n" + "=" * 70)
    logger.info("[PUBLISHER READY] Bus started on 127.0.0.22 (local service table)")
    logger.info("[SD DISCOVERY] Listening for SD Find messages on multicast (224.224.224.245:30490)")
    logger.info("[ADVERTISING] Will announce Service=0x1234, Instance=0x0001")
    logger.info("=" * 70 + "\n")
    logger.info("Publisher bus started (AFTER subscriber)")

    # Give the subscriber time to receive SD Offer and establish subscription.
    await asyncio.sleep(2.0)

    test_payload: dict = {"data": "sub-first-test", "ts": datetime.now().isoformat()}
    logger.info("\n" + "=" * 70)
    logger.info("[SD PROTOCOL] Publisher sending message to discovered subscribers")
    logger.info("=" * 70 + "\n")
    await bus.publish(EventMessage(topic=topic_a, payload=test_payload))
    logger.info("Test publish sent")

    await asyncio.sleep(2.0)
    await bus.stop()
    logger.info("Publisher bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
