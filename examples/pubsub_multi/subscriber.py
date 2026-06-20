#!/usr/bin/env python3
"""tinySOA TCP EventBus subscriber (engineering-grade).

Connects to a running ``TCPEventBusServer`` (see ``server.py``), subscribes to a
topic, and logs every event it receives until interrupted. Each instance stamps
its output with ``subscriber_id`` so multiple subscribers are distinguishable.

Run (from the ``tinySOA`` directory; start ``server.py`` first):

    PYTHONPATH=../src:src python examples/pubsub_multi/subscriber.py sub-1 \\
        --topic demo.topic

Exit code 0 on clean shutdown (SIGINT/SIGTERM), 1 if the broker is unreachable.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from datetime import datetime
from typing import Optional, Sequence

from tinysoa.eventbus import EventMessage, TCPEventBusClient

logger = logging.getLogger("tinysoa.example.pubsub.subscriber")

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA TCP subscriber")
    parser.add_argument("subscriber_id", help="ID stamped on every received message")
    parser.add_argument("--topic", default="demo.topic", help="topic to subscribe to (default: demo.topic)")
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

    def handle(msg: EventMessage) -> None:
        # NOTE: the TCP client invokes handlers synchronously from its reader
        # thread, so a plain (non-async) handler is the correct shape here.
        logger.info(
            "subscriber=%s topic=%s payload=%s", args.subscriber_id, msg.topic, msg.payload
        )

    sub = client.subscribe(args.topic, handle)
    logger.info(
        "subscriber %s subscribed to '%s' on %s:%d", args.subscriber_id, args.topic, args.host, args.port
    )

    def _graceful(signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
        logger.info("received signal %d, shutting down...", signum)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _graceful)
    signal.signal(signal.SIGTERM, _graceful)

    try:
        signal.pause()  # block until a signal handler raises SystemExit
    except SystemExit:
        return 0
    finally:
        client.unsubscribe(sub)
        client.close()
        logger.info("subscriber %s disconnected", args.subscriber_id)


if __name__ == "__main__":
    sys.exit(main())
