#!/usr/bin/env python3
"""Custom interceptor + Auth demo -- tinySOA Lab 6 (SPI extension point).

The interceptor chain is tinySOA's seam for cross-cutting concerns (auth,
tracing, timing, metrics, ...). This self-contained example shows how to *use*
that seam by writing your own interceptors and composing them with the built-in
``AuthInterceptor``:

  * ``CorrelationIdInterceptor`` (custom, priority 1) -- stamps a correlation id
    onto every invocation; lowest priority so it runs first and every
    downstream stage can read it.
  * ``AuthInterceptor`` (built-in, priority 5) -- checks the ``Authorization``
    request header; on mismatch it SHORT-CIRCUITS the chain by setting
    ``context.error`` and returning without calling ``next_invoker``.
  * ``TimingInterceptor`` (custom, priority 15) -- measures wall-clock duration
    with ``try/finally`` so its exit stamp is recorded on BOTH the success and
    the exception path.

Priority is ascending: lower runs first on the way in.

Three scenarios are played out and the per-invocation execution order is
printed, so you can see exactly:

  1. authorized   -- valid token: request flows through every stage -> response.
  2. unauthorized -- wrong token: Auth short-circuits, Timing/invoker never run.
  3. business err -- invoker raises: the exception propagates up the chain
     untouched (never swallowed). Note how Timing (try/finally) still records
     its exit while Correlation (plain await) does not -- the raise unwinds
     straight past it.

Self-contained & deterministic (in-memory, no network).

Run (from the repo root, both source roots on PYTHONPATH):

    PYTHONPATH=src:tinySOA/src python tinySOA/examples/interceptor_auth/app.py
    PYTHONPATH=src:tinySOA/src python tinySOA/examples/interceptor_auth/app.py --scenario unauthorized
    PYTHONPATH=src:tinySOA/src python tinySOA/examples/interceptor_auth/app.py --log-level DEBUG

Exit code 0 on success, 130 on Ctrl-C.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from typing import Any, Awaitable, Callable, List, Optional, Sequence, Tuple
from uuid import uuid4

from tinysoa.core.model import Message, Method, Service
from tinysoa.spi.interceptor import (
    AuthInterceptor,
    Interceptor,
    InterceptorChain,
    InvocationContext,
)

logger = logging.getLogger("tinysoa.example.interceptor_auth")

#: Token the built-in AuthInterceptor demands; clients must send it in the
#: ``Authorization`` header to pass the gate.
VALID_TOKEN = "Bearer demo-secret"

#: The single service/method this demo invokes.
_METHOD = Method(name="greet", id=1)
_SERVICE = Service(name="greeter", id=42, version="1.0.0", methods=[_METHOD])


# ---------------------------------------------------------------------------
# Custom interceptors
# ---------------------------------------------------------------------------


class CorrelationIdInterceptor(Interceptor):
    """Stamp a correlation id onto every invocation (custom interceptor).

    Priority 1 -> runs FIRST, so every later stage and the invoker itself can
    read ``context.metadata["correlation_id"]`` for end-to-end tracing. It uses
    a plain ``await next_invoker(context)`` (no try/finally), so on the
    exception path its ``:exit`` stamp is skipped -- see scenario 3.
    """

    def __init__(self, trace: List[str], priority: int = 1) -> None:
        self._trace = trace
        self._priority = priority

    @property
    def priority(self) -> int:
        return self._priority

    async def intercept(
        self,
        context: InvocationContext,
        next_invoker: Callable[[InvocationContext], Awaitable[None]],
    ) -> None:
        self._trace.append("correlation:enter")
        if not context.metadata.get("correlation_id"):
            context.metadata["correlation_id"] = f"corr-{uuid4().hex[:8]}"
        await next_invoker(context)
        self._trace.append("correlation:exit")


class TimingInterceptor(Interceptor):
    """Measure wall-clock duration of each invocation (custom interceptor).

    Priority 15 -> runs last before the invoker. Uses ``try/finally`` so the
    ``:exit`` stamp and duration are recorded on BOTH the success path and the
    exception path -- contrast with ``CorrelationIdInterceptor``.
    """

    def __init__(
        self, trace: List[str], durations: List[float], priority: int = 15
    ) -> None:
        self._trace = trace
        self._durations = durations
        self._priority = priority

    @property
    def priority(self) -> int:
        return self._priority

    async def intercept(
        self,
        context: InvocationContext,
        next_invoker: Callable[[InvocationContext], Awaitable[None]],
    ) -> None:
        self._trace.append("timing:enter")
        start = time.perf_counter()
        try:
            await next_invoker(context)
        finally:
            self._durations.append((time.perf_counter() - start) * 1000.0)
            self._trace.append("timing:exit")


# ---------------------------------------------------------------------------
# Business invoker (chain terminator)
# ---------------------------------------------------------------------------


async def greet_invoker(context: InvocationContext) -> None:
    """Greet the caller -- or blow up on the trigger name ``boom``."""
    name = context.request.payload.get("name", "stranger")
    if name == "boom":
        raise RuntimeError("greeting service exploded on purpose")
    context.set_response(
        Message(
            payload={
                "greeting": f"hello, {name}!",
                "correlation_id": context.metadata.get("correlation_id"),
            }
        )
    )


# ---------------------------------------------------------------------------
# Wiring + invocation helpers
# ---------------------------------------------------------------------------


def build_chain(
    required_token: str = VALID_TOKEN,
) -> Tuple[InterceptorChain, List[str], List[float]]:
    """Build a fresh chain: Correlation(1) -> Auth(5) -> Timing(15) -> greet.

    Returns the chain plus the shared ``trace`` / ``durations`` collectors the
    custom interceptors write into, so callers (and tests) can observe order.
    """
    trace: List[str] = []
    durations: List[float] = []
    chain = InterceptorChain(greet_invoker)
    chain.add_interceptor(CorrelationIdInterceptor(trace))
    chain.add_interceptor(AuthInterceptor(required_token=required_token))
    chain.add_interceptor(TimingInterceptor(trace, durations))
    return chain, trace, durations


def _make_context(payload: Any, token: Optional[str]) -> InvocationContext:
    headers = {"Authorization": token} if token else {}
    return InvocationContext(
        service=_SERVICE,
        method=_METHOD,
        request=Message(payload=payload, headers=headers),
    )


async def invoke(
    chain: InterceptorChain, payload: Any, token: Optional[str]
) -> InvocationContext:
    """Run ``payload``/``token`` through ``chain`` and return the context.

    Raises whatever the invoker raises (business errors propagate). A failed
    AuthInterceptor does NOT raise -- it sets ``context.error`` (short-circuit),
    so callers check ``context.error`` after a normal return.
    """
    ctx = _make_context(payload, token)
    await chain.invoke(ctx)
    return ctx


# ---------------------------------------------------------------------------
# Scenario runner (human-facing narrative)
# ---------------------------------------------------------------------------

#: choice -> (label, payload, Authorization token)
SCENARIOS: "dict[str, Tuple[str, dict, Optional[str]]]" = {
    "authorized": (
        "valid token: request flows through the whole chain",
        {"name": "World"},
        VALID_TOKEN,
    ),
    "unauthorized": (
        "wrong token: Auth short-circuits before Timing/invoker",
        {"name": "World"},
        "Bearer definitely-wrong",
    ),
    "error": (
        "valid token but invoker raises: exception propagates through the chain",
        {"name": "boom"},
        VALID_TOKEN,
    ),
}


async def run_scenario(name: str) -> None:
    label, payload, token = SCENARIOS[name]
    chain, trace, durations = build_chain()
    logger.info("=" * 64)
    logger.info("SCENARIO [%s]: %s", name, label)

    outcome: str
    try:
        ctx = await invoke(chain, payload, token)
    except Exception as exc:  # noqa: BLE001 -- demo surfaces propagated errors
        outcome = f"RAISED {type(exc).__name__}: {exc}"
    else:
        if ctx.error is not None:
            outcome = f"SHORT-CIRCUITED by Auth: {ctx.error}"
        else:
            outcome = f"OK -> {ctx.response.payload}"

    logger.info(
        "order  : Correlation(1) -> Auth(5) -> Timing(15) -> greet "
        "(lower priority runs first)"
    )
    logger.info("trace  : %s", " -> ".join(trace) or "(empty)")
    logger.info("dur ms : %s", [round(d, 4) for d in durations])
    logger.info("outcome: %s", outcome)


async def run(scenario: str) -> None:
    logger.info("tinySOA Lab 6 -- custom interceptor + Auth demo")
    logger.info(
        "chain  : CorrelationIdInterceptor(1) -> AuthInterceptor(5) "
        "-> TimingInterceptor(15) -> greet_invoker"
    )
    names = (
        ["authorized", "unauthorized", "error"] if scenario == "all" else [scenario]
    )
    for n in names:
        await run_scenario(n)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="tinySOA Lab 6 -- custom interceptor + Auth demo (SPI extension point)"
    )
    parser.add_argument(
        "--scenario",
        choices=["authorized", "unauthorized", "error", "all"],
        default="all",
        help="which scenario to run (default: all)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging verbosity (default: INFO)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        asyncio.run(run(args.scenario))
    except KeyboardInterrupt:
        logger.info("interrupted")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
