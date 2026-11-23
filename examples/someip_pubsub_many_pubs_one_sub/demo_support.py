"""Logging and teardown helpers shared by the multi-publisher demo."""

from __future__ import annotations

import asyncio
import logging
from typing import Tuple

_LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

#: Valid logging level tokens accepted on the CLI.
LOG_LEVELS: Tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")


def configure_logging(level: str = "INFO", name: str = "someip.demo") -> logging.Logger:
    """Configure root logging once and return a named logger."""
    logging.basicConfig(level=level, format=_LOG_FORMAT, datefmt=_LOG_DATEFMT)
    return logging.getLogger(name)


def install_quiet_teardown() -> None:
    """Silence benign teardown races in the underlying SOME/IP stack.

    When ``SomeIPEventBus.stop()`` closes the SD transports, two kinds of
    post-delivery noise can surface (delivery has already succeeded by then):

    * an in-flight periodic ``sendto`` touching the loop after shutdown begins,
      raising ``AttributeError: 'NoneType' object has no attribute
      'call_exception_handler'``;
    * the SD announcer's ``connection_lost`` double-stopping an already-stopped
      task, raising ``RuntimeError: task already stopped``.

    Both originate in the pysomeip SD layer during teardown only. Install this
    handler to drop just those two messages while still logging every real
    error.
    """
    loop = asyncio.get_running_loop()

    def _handler(loop, context) -> None:  # type: ignore[no-untyped-def]
        exc = context.get("exception")
        if exc is not None:
            message = str(exc)
            if "call_exception_handler" in message or "task already stopped" in message:
                return
        loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)
