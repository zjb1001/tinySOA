#!/usr/bin/env python3
"""tinySOA TCP EventBus subscriber (engineering-grade).

Connects to a running TCP broker (see ``server.py``), subscribes to a topic,
and logs every event it receives until interrupted. Each instance stamps its
output with ``subscriber_id`` so multiple subscribers are distinguishable.

Run (from the ``tinySOA`` directory; start ``server.py`` first):

    PYTHONPATH=.:src:third_party/pysomeip/src python -m examples.tcp_pubsub_one_pub_many_subs.subscriber sub-1 \\
        --topic demo.topic

Exit code 0 on clean shutdown (SIGINT/SIGTERM), 1 if the broker is unreachable.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Optional, Sequence

from tinysoa.eventbus import EventMessage, TCPEventBus

logger = logging.getLogger("tinysoa.example.pubsub.subscriber")

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA TCP subscriber")
    parser.add_argument("subscriber_id", help="ID stamped on every received message")
    parser.add_argument(
        "--topic",
        default="demo.topic",
        help="topic to subscribe to (default: demo.topic)",
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

    async def handle(msg: EventMessage) -> None:
        logger.info(
            "subscriber=%s topic=%s payload=%s",
            args.subscriber_id,
            msg.topic,
            msg.payload,
        )

    subscriber = bus.subscriber(args.topic, handle)
    await bus.register(subscriber)
    logger.info(
        "subscriber %s subscribed to '%s' on %s:%d",
        args.subscriber_id,
        args.topic,
        args.host,
        args.port,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await bus.unregister(subscriber)
        await bus.stop()
        logger.info("subscriber %s disconnected", args.subscriber_id)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
