#!/usr/bin/env python3
"""tinySOA TCP publisher with caller-identity header (engineering-grade).

Like ``examples/tcp_pubsub_one_to_many/publisher.py``, but stamps every event with a
``publisher_id`` (positional arg) in the payload AND in an ``x-publisher-id``
header — so a single subscriber can distinguish multiple publishers on the same
topic.

Run (from the ``tinySOA`` directory; start the TCP broker first):

    PYTHONPATH=.:src:third_party/pysomeip/src python -m examples.tcp_pubsub_many_to_one.publisher_with_id \\
        pub-A --topic demo.topic --count 5 --interval 0.5

Exit code 0 on success, 1 if the broker is unreachable.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional, Sequence

from tinysoa.eventbus import EventMessage, TCPEventBus

logger = logging.getLogger("tinysoa.example.multipub.publisher")

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA TCP publisher with caller ID")
    parser.add_argument("publisher_id", help="ID stamped into every published event")
    parser.add_argument(
        "--topic",
        default="demo.topic",
        help="topic to publish on (default: demo.topic)",
    )
    parser.add_argument(
        "--count", type=int, default=5, help="number of messages to send (default: 5)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="seconds between messages (default: 1.0)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="broker host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="broker port (default: 8765)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=_LOG_LEVELS,
        help="logging verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    bus = TCPEventBus(host=args.host, port=args.port)
    try:
        await bus.start()
    except OSError as exc:
        logger.error("cannot connect to broker %s:%d: %s", args.host, args.port, exc)
        return 1

    logger.info(
        "connected to %s:%d, publishing %d events as '%s' on '%s'",
        args.host,
        args.port,
        args.count,
        args.publisher_id,
        args.topic,
    )
    try:
        for i in range(args.count):
            payload = {
                "from": args.publisher_id,
                "i": i,
                "ts": datetime.now().isoformat(),
            }
            await bus.publish(
                EventMessage(
                    topic=args.topic,
                    payload=payload,
                    headers={"x-publisher-id": args.publisher_id},
                )
            )
            logger.info(
                "published [%s] -> %s: %s", args.publisher_id, args.topic, payload
            )
            if i < args.count - 1:
                await asyncio.sleep(args.interval)
    finally:
        await bus.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
