"""ST-004 publisher: service-restart resilience — publisher restarts, subscriber survives.

Verifies that after a publisher stops and restarts on the same service identity,
the subscriber re-discovers it and receives new messages without restarting.
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

logger = configure_logging("ST-004-PUB")


async def main() -> None:
    topic_a = "test.topic.a"
    mappings = {
        topic_a: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    install_quiet_exception_handler(logger)

    bus = SomeIPEventBus(
        mappings=mappings, local_ip="127.0.0.32", publisher_port=34020,
    )

    await bus.start()
    logger.info("\n" + "=" * 70)
    logger.info("[PUBLISHER READY] Bus started on 127.0.0.32:34020")
    logger.info("[SD DISCOVERY] Advertising Service=0x1234, Instance=0x0001")
    logger.info("=" * 70 + "\n")

    # Wait for subscriber to subscribe.
    await asyncio.sleep(8.0)

    msg1_payload: dict = {"data": "after-restart-1", "ts": datetime.now().isoformat()}
    logger.info("\n" + "=" * 70)
    logger.info("[SENDING] First message after potential restart")
    logger.info("=" * 70 + "\n")
    await bus.publish(EventMessage(topic=topic_a, payload=msg1_payload))

    await asyncio.sleep(1.0)

    msg2_payload: dict = {"data": "validation", "ts": datetime.now().isoformat()}
    logger.info("\n" + "=" * 70)
    logger.info("[SENDING] Validation message")
    logger.info("=" * 70 + "\n")
    await bus.publish(EventMessage(topic=topic_a, payload=msg2_payload))

    await asyncio.sleep(2.0)
    await bus.stop()
    logger.info("Publisher bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
