#!/usr/bin/env python3
"""tinySOA TCP EventBus publisher (engineering-grade).

Connects to a running ``TCPEventBusServer`` (see ``server.py``) and publishes a
short burst of timestamped events on a topic, then exits.

Run (from the ``tinySOA`` directory; start ``server.py`` first):

    PYTHONPATH=../src:src python examples/pubsub_multi/publisher.py \\
        --topic demo.topic --count 5 --interval 1.0

Exit code 0 on success, 1 if the broker is unreachable.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from typing import Optional, Sequence

from tinysoa.eventbus import EventMessage, TCPEventBusClient

logger = logging.getLogger("tinysoa.example.pubsub.publisher")

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA TCP publisher")
    parser.add_argument("--topic", default="demo.topic", help="topic to publish on (default: demo.topic)")
    parser.add_argument("--count", type=int, default=5, help="number of messages to send (default: 5)")
    parser.add_argument(
        "--interval", type=float, default=1.0, help="seconds between messages (default: 1.0)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="broker host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="broker port (default: 8765)")
    parser.add_argument(
        "--log-level", default="INFO", choices=_LOG_LEVELS, help="logging verbosity (default: INFO)"
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        client = TCPEventBusClient(host=args.host, port=args.port)
    except OSError as exc:
        logger.error("cannot connect to broker %s:%d: %s", args.host, args.port, exc)
        return 1

    logger.info("connected to %s:%d, publishing %d events on '%s'", args.host, args.port, args.count, args.topic)
    try:
        for i in range(args.count):
            payload = {"i": i, "ts": datetime.now().isoformat()}
            client.publish(EventMessage(topic=args.topic, payload=payload))
            logger.info("published to %s: %s", args.topic, payload)
            if i < args.count - 1:
                time.sleep(args.interval)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
