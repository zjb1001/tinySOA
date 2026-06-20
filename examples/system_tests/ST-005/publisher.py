"""ST-005 publisher: high-throughput stress test — 1000 messages at 20ms intervals.

Verifies the SOME/IP stack handles sustained message throughput without crashes or
excessive UDP loss on loopback.
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

logger = configure_logging("ST-005-PUB")


async def main() -> None:
    topic_a = "test.topic.a"
    mappings = {
        topic_a: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    install_quiet_exception_handler(logger)

    bus = SomeIPEventBus(
        mappings=mappings, local_ip="127.0.0.42", publisher_port=35020,
    )

    await bus.start()
    logger.info("\n" + "=" * 70)
    logger.info("[STRESS TEST PUBLISHER] Bus started on 127.0.0.42:35020")
    logger.info("[READY] Will publish 1000 messages at 20ms intervals")
    logger.info("Expected throughput: 50 msg/sec")
    logger.info("=" * 70 + "\n")

    # Wait for subscriber to be ready.
    await asyncio.sleep(8.0)

    logger.info("[STARTING] Publishing message stream...")
    start_time = asyncio.get_event_loop().time()

    for seq in range(1000):
        payload: dict = {
            "seq": seq,
            "ts": datetime.now().isoformat(),
            "data": f"stress-test-{seq}",
        }
        await bus.publish(EventMessage(topic=topic_a, payload=payload))
        if (seq + 1) % 100 == 0:
            logger.info("[PROGRESS] Published %d/1000 messages", seq + 1)
        await asyncio.sleep(0.02)

    elapsed = asyncio.get_event_loop().time() - start_time
    logger.info("\n" + "=" * 70)
    logger.info("[PUBLISHING COMPLETE]")
    logger.info("Published 1000 messages in %.2f seconds", elapsed)
    logger.info("Actual throughput: %.1f msg/sec", 1000.0 / elapsed)
    logger.info("=" * 70 + "\n")

    await asyncio.sleep(2.0)
    await bus.stop()
    logger.info("Publisher bus stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
