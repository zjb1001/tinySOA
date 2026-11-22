#!/usr/bin/env python3
"""SOME/IP Calculator Server — framework-based RPC service.

The application only registers logical method names and async handlers; SD,
REQUEST/RESPONSE, JSON encoding, and error responses are handled by
``SomeIPMethodDispatcher``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Optional, Sequence

from tinysoa.eventbus import SomeIPService

from ._common import LOCAL_IP, SERVER_PORT, SERVICE_ID, binding

logger = logging.getLogger("calc.server")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOME/IP Calculator Server")
    parser.add_argument(
        "--host", default=LOCAL_IP, help=f"bind address (default: {LOCAL_IP})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=SERVER_PORT,
        help=f"listen port (default: {SERVER_PORT})",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=LOG_LEVELS, help="logging verbosity"
    )
    return parser.parse_args(argv)


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    service = SomeIPService(
        binding(server_port=args.port),
        local_ip=args.host,
        is_publisher=True,
    )

    @service.method("add")
    async def add(payload: dict) -> dict:
        return {"result": float(payload["a"]) + float(payload["b"])}

    @service.method("subtract")
    async def subtract(payload: dict) -> dict:
        return {"result": float(payload["a"]) - float(payload["b"])}

    @service.method("multiply")
    async def multiply(payload: dict) -> dict:
        return {"result": float(payload["a"]) * float(payload["b"])}

    await service.start()
    logger.info(
        "Calculator Server started — service_id=0x%04x on %s:%d",
        SERVICE_ID,
        args.host,
        args.port,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        await service.stop()
        logger.info("Calculator Server stopped")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
