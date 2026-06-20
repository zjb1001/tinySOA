"""Regression tests for the interceptor_auth example (Lab 6).

Pins the public behavior of the demo so refactors stay honest:

  * an authorized request reaches the invoker and returns a greeting, with
    interceptors executed in ascending-priority order;
  * an unauthorized request is short-circuited by ``AuthInterceptor``
    (``context.error`` set, the downstream interceptor and invoker never run);
  * a raised business error propagates through the chain untouched -- a
    ``try/finally`` interceptor still observes the exit, a plain-``await`` one
    does not.
"""
from __future__ import annotations

import pytest

from examples.interceptor_auth.app import VALID_TOKEN, build_chain, invoke


@pytest.mark.asyncio
async def test_authorized_request_runs_full_chain_in_priority_order() -> None:
    chain, trace, durations = build_chain()

    ctx = await invoke(chain, {"name": "World"}, VALID_TOKEN)

    assert ctx.error is None
    assert ctx.response is not None
    assert ctx.response.payload["greeting"] == "hello, World!"
    # correlation id injected by the first interceptor, visible to the invoker
    assert ctx.response.payload["correlation_id"] is not None
    # ascending priority on the way in, symmetric exits on the way out
    assert trace == [
        "correlation:enter",
        "timing:enter",
        "timing:exit",
        "correlation:exit",
    ]
    assert len(durations) == 1
    assert durations[0] >= 0.0


@pytest.mark.asyncio
async def test_unauthorized_request_short_circuits_at_auth() -> None:
    chain, trace, durations = build_chain()

    ctx = await invoke(chain, {"name": "World"}, "Bearer definitely-wrong")

    # Auth set the error and returned WITHOUT calling next_invoker.
    assert isinstance(ctx.error, Exception)
    assert "Unauthorized" in str(ctx.error)
    assert ctx.response is None
    # Timing (priority 15) and the invoker never ran; only Correlation entered.
    assert trace == ["correlation:enter", "correlation:exit"]
    assert durations == []


@pytest.mark.asyncio
async def test_business_error_propagates_unchanged_through_chain() -> None:
    chain, trace, durations = build_chain()

    # The invoker raises; the exception must surface here, never swallowed.
    with pytest.raises(RuntimeError, match="exploded"):
        await invoke(chain, {"name": "boom"}, VALID_TOKEN)

    # Timing used try/finally -> exit recorded; Correlation used plain await ->
    # its exit was skipped because the raise unwound past it.
    assert "timing:exit" in trace
    assert "correlation:exit" not in trace
    assert len(durations) == 1


def test_main_runs_clean_and_returns_zero() -> None:
    """``main(['--scenario','authorized'])`` exits 0 (smoke for the CLI)."""
    from examples.interceptor_auth.app import main

    rc = main(["--scenario", "authorized", "--log-level", "ERROR"])
    assert rc == 0
