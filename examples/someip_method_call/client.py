#!/usr/bin/env python3
"""SOME/IP Calculator Client — framework-based RPC client.

The application calls logical ``service`` / ``method`` names; SD discovery,
REQUEST/RESPONSE, session matching, JSON encoding, and timeouts are handled by
``SomeIPMethodInvoker``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from typing import Optional, Sequence

from tinysoa.eventbus import SomeIPMethodInvoker

from ._common import CLIENT_PORT, LOCAL_IP, SERVICE_NAME, binding

logger = logging.getLogger("calc.client")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

TEST_CASES = [
    ("add", {"a": 10, "b": 7}, 17),
    ("subtract", {"a": 50, "b": 18}, 32),
    ("multiply", {"a": 6, "b": 8}, 48),
]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOME/IP Calculator Client")
    parser.add_argument(
        "--host", default=LOCAL_IP, help=f"local bind address (default: {LOCAL_IP})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=CLIENT_PORT,
        help=f"local unicast port (default: {CLIENT_PORT})",
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

    invoker = SomeIPMethodInvoker(
        binding(local_port=args.port, timeout=5.0),
        local_ip=args.host,
    )
    try:
        await invoker.start()
    except Exception as exc:
        logger.error("cannot start SOME/IP invoker: %s", exc)
        return 1

    logger.info("Calculator Client started — looking for service %r", SERVICE_NAME)
    passed = 0
    failed = 0
    try:
        for method_name, operands, expected in TEST_CASES:
            started = time.monotonic()
            try:
                response = await invoker.invoke(SERVICE_NAME, method_name, operands)
                elapsed = time.monotonic() - started
                actual = response.payload["result"]
                ok = abs(actual - expected) < 0.001
                if ok:
                    passed += 1
                else:
                    failed += 1
                logger.info(
                    "%s  %s(%s) = %s  (expected %s)  %.1fms",
                    "PASS" if ok else "FAIL",
                    method_name,
                    operands,
                    actual,
                    expected,
                    elapsed * 1000,
                )
            except asyncio.TimeoutError:
                failed += 1
                logger.error("TIMEOUT  %s(%s) — no response", method_name, operands)
            except Exception as exc:
                failed += 1
                logger.error("ERROR  %s(%s) — %s", method_name, operands, exc)
    finally:
        await invoker.stop()

    logger.info(
        "Results: %d passed, %d failed, %d total",
        passed,
        failed,
        passed + failed,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(1)
