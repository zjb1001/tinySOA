#!/usr/bin/env python3
"""tinySOA TCP EventBus broker (engineering-grade).

Runs a ``TCPEventBusServer`` that fans out published events to every client
subscribed to a topic. Intended for local demos / dev; the server is not
hardened for production (no auth, backpressure or persistence).

Run (from the ``tinySOA`` directory, tinysoa + someip resolve from source):

    PYTHONPATH=../src:src python examples/pubsub_multi/server.py \\
        --host 127.0.0.1 --port 8765 --log-level INFO

Exit code 0 on clean shutdown (SIGINT/SIGTERM), 1 if the port is unavailable.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from typing import Optional, Sequence

from tinysoa.eventbus import TCPEventBusServer

logger = logging.getLogger("tinysoa.example.pubsub.server")

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA TCP EventBus broker")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="listen port (default: 8765)")
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

    server = TCPEventBusServer(host=args.host, port=args.port)
    try:
        server.start()
    except OSError as exc:
        logger.error("failed to bind %s:%d: %s", args.host, args.port, exc)
        return 1

    logger.info("TCP EventBus server listening on %s:%d", args.host, args.port)

    def _graceful(signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
        logger.info("received signal %d, shutting down...", signum)
        server.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _graceful)
    signal.signal(signal.SIGTERM, _graceful)

    try:
        signal.pause()  # block until a signal handler raises SystemExit
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    finally:
        server.stop()


if __name__ == "__main__":
    sys.exit(main())
