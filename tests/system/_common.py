"""System test shared utilities — single source for boilerplate.

Import this once from any ``system_tests/ST-*`` script to eliminate the three
pieces of duplicated boilerplate that currently appear in every test file:

* ``setup_path()`` — replaces ``sys.path.append(../../../src)`` hacks (24 files).
* ``configure_logging(name, level)`` — replaces ad-hoc ``logging.basicConfig``
  (34 files).
* ``install_quiet_exception_handler(logger)`` — replaces the identical ~12-line
  teardown-noise suppressor (15 files).

Usage (replace ~20 lines of boilerplate with ~6)::

    from _common import setup_path, configure_logging, install_quiet_exception_handler

    setup_path()
    logger = configure_logging("ST-001")

    async def main():
        install_quiet_exception_handler(logger)
        ...
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Tuple

# Resolve both source roots from this file's position in the repo tree:
#   .../tinySOA/tests/system/_common.py
_HERE = Path(__file__).resolve().parent                       # tests/system/
_REPO_ROOT = _HERE.parents[1]                                 # .../tinySOA
_TINYSOA_SRC = _REPO_ROOT / "src"                             # tinySOA/src
# pysomeip is vendored as a git submodule under third_party/.
_SOMEIP_SRC = _REPO_ROOT / "third_party" / "pysomeip" / "src"

LOG_LEVELS: Tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")

#: Standard log format shared by all system tests.
_LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_path() -> None:
    """Add ``tinysoa`` and ``someip`` source roots to ``sys.path``.

    Both packages resolve from source (no pip install) — equivalent to
    ``export PYTHONPATH=src:third_party/pysomeip/src``.
    Call once at module level before any framework imports.
    """
    for p in (str(_TINYSOA_SRC), str(_SOMEIP_SRC)):
        if p not in sys.path:
            sys.path.insert(0, p)


def configure_logging(name: str, level: str = "INFO") -> logging.Logger:
    """Configure root logging once and return a named logger.

    Safe to call at module level: ``logging.basicConfig`` is a no-op after the
    first call.
    """
    logging.basicConfig(level=level, format=_LOG_FORMAT, datefmt=_LOG_DATEFMT)
    return logging.getLogger(name)


def install_quiet_exception_handler(logger: logging.Logger) -> None:
    """Suppress known benign shutdown races in the pysomeip SD stack.

    During ``SomeIPEventBus.stop()``, transport closures can trigger in-flight
    callbacks that raise:

    * ``RuntimeError: task already stopped`` — SD announcer double-stop.
    * ``AttributeError`` on ``sendto`` / ``call_exception_handler`` — transport
      already closed before a periodic send fires.

    Delivery has already succeeded by then.  Install this handler to drop only
    that noise while letting every real error through.

    Must be called from inside the running event loop (i.e. inside ``async def
    main()``), not at module level.
    """
    loop = asyncio.get_running_loop()
    default_handler = loop.get_exception_handler() or loop.default_exception_handler

    def _handler(loop_ref, ctx) -> None:  # type: ignore[no-untyped-def]
        exc = ctx.get("exception")
        if exc is None:
            default_handler(ctx)
            return
        message = str(exc)
        if (
            "task already stopped" in message
            or "sendto" in message
            or "call_exception_handler" in message
        ):
            logger.debug("suppressed benign teardown noise: %s", exc)
            return
        default_handler(ctx)

    loop.set_exception_handler(_handler)
