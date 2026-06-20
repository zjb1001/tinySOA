"""
Cross-process SOME/IP publisher.

Runs as its OWN OS process. Owns a SOME/IP service (via tinySOA's SomeIPEventBus
on top of pysomeip), announces it through Service Discovery, and publishes
`demo.cross_process` events. A subscriber in a DIFFERENT process receives them.

Run (from repo root, no install needed — both packages resolve from source):

    PYTHONPATH=src:tinySOA/src python tinySOA/examples/cross_process_someip/publisher.py [count] [interval]

Exit code 0 on clean shutdown.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from tinysoa.eventbus.message import EventMessage
from tinysoa.eventbus.someip import SomeIPEventBus

from examples.cross_process_someip import (
    LOCAL_IP,
    MAPPINGS,
    PUBLISHER_PORT_BASE,
    TOPIC,
    quiet_teardown,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("PUBLISHER")


async def main() -> None:
    quiet_teardown()
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.8

    # is_publisher=True: this process advertises the service via SD.
    bus = SomeIPEventBus(
        MAPPINGS,
        local_ip=LOCAL_IP,
        publisher_port=PUBLISHER_PORT_BASE,
        is_publisher=True,
    )
    logger.info("starting (service 0x2222, port base %d), will publish %d events @ %.2fs",
                PUBLISHER_PORT_BASE, count, interval)
    await bus.start()

    # Let the SD Offer propagate before we start notifying, so a subscriber
    # that is already listening can match the service.
    await asyncio.sleep(1.5)

    try:
        for i in range(count):
            msg = EventMessage(topic=TOPIC, payload={"seq": i, "msg": f"hello-{i}"})
            await bus.publish(msg)
            logger.info("PUB seq=%d", i)
            await asyncio.sleep(interval)
        # Give in-flight notifications a moment to land before teardown.
        await asyncio.sleep(1.5)
    finally:
        await bus.stop()
        logger.info("stopped after publishing %d events", count)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
