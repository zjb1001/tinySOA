"""SOME/IP one-to-many publisher."""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime

from tinysoa.config import create_event_bus
from tinysoa.eventbus import EventMessage

from ._common import SERVICE_ID, TOPIC, publisher_config

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
logger = logging.getLogger("someip.one_to_many.publisher")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="tinySOA SOME/IP one-to-many publisher"
    )
    parser.add_argument(
        "--count", type=int, default=20, help="messages to publish (default: 20)"
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, help="seconds between messages"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=LOG_LEVELS,
        help="logging verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


async def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | PUBLISHER | %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.count <= 0:
        logger.error("--count must be positive")
        return 2

    bus = create_event_bus(publisher_config())
    logger.info(
        "starting service=0x%04x topic=%s count=%d interval=%.1fs",
        SERVICE_ID,
        TOPIC,
        args.count,
        args.interval,
    )
    await bus.start()
    logger.info("SD Offer started; waiting for subscribers")
    try:
        await asyncio.sleep(2.0)
        for seq in range(args.count):
            payload = {
                "seq": seq,
                "msg": f"hello-{seq}",
                "ts": datetime.now().isoformat(),
            }
            await bus.publish(EventMessage(topic=TOPIC, payload=payload))
            logger.info("published seq=%d", seq)
            if seq < args.count - 1:
                await asyncio.sleep(args.interval)
        await asyncio.sleep(1.0)
    finally:
        await bus.stop()
        logger.info("stopped after %d messages", args.count)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(0) from None
