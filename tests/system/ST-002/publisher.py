"""ST-002 publisher: warmup + validation publish for the late-subscriber test.

Run as its own OS process (together with ``run_test.py`` orchestrator).

Run:
    python tests/system_tests/ST-002/publisher.py   # from repo root; _common adds paths
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

# Make _common importable whether run as a bare script from this dir or via -m.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> system_tests/
from _common import configure_logging, install_quiet_exception_handler, setup_path  # noqa: E402
setup_path()  # -> adds tinysoa/src + pysomeip/src

from tinysoa.eventbus.message import EventMessage  # noqa: E402
from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping  # noqa: E402

logger = configure_logging("ST-002-PUB")

TEST_TOPIC = "test.topic.a"


async def main() -> None:
    """Publish a warmup event (triggers SD Offer), wait for subscriber, then validate."""
    install_quiet_exception_handler(logger)

    mappings = {
        TEST_TOPIC: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    bus = SomeIPEventBus(
        mappings=mappings, local_ip="127.0.0.11", publisher_port=32010,
    )
    await bus.start()
    logger.info("Publisher bus started")

    # Warmup publish to trigger SD Offer
    warmup_payload: dict = {"data": "warmup", "ts": datetime.now().isoformat()}
    await bus.publish(EventMessage(topic=TEST_TOPIC, payload=warmup_payload))
    logger.info("Warmup publish sent")

    # Let the subscriber start and complete its internal SD delay
    await asyncio.sleep(8.0)

    validation_payload: dict = {"data": "late-sub", "ts": datetime.now().isoformat()}
    await bus.publish(EventMessage(topic=TEST_TOPIC, payload=validation_payload))
    logger.info("Validation publish sent")

    await asyncio.sleep(2.0)
    await bus.stop()
    logger.info("Publisher bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
