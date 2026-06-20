import time
import pytest
import asyncio

from tinysoa.policies.retry import (
    RetryPolicy,
    RetryError,
    constant_backoff,
    linear_backoff,
    exponential_backoff,
    full_jitter,
)
from tinysoa.policies.timeout import TimeoutPolicy, TimeoutError
from tinysoa.policies.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitBreakerState


@pytest.mark.asyncio
async def test_retry_success_first_try():
    calls = {"count": 0}

    async def fn():
        calls["count"] += 1
        return "ok"

    policy = RetryPolicy(max_attempts=3)
    result = await policy.run(fn)

    assert result == "ok"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_retry_with_failures_then_success():
    calls = {"count": 0}

    async def fn():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ValueError("fail")
        return "ok"

    policy = RetryPolicy(max_attempts=5, backoff=constant_backoff(0))
    result = await policy.run(fn)

    assert result == "ok"
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_retry_exhausted():
    async def fn():
        raise RuntimeError("always fail")

    policy = RetryPolicy(max_attempts=2, backoff=constant_backoff(0))

    with pytest.raises(RetryError):
        await policy.run(fn)


@pytest.mark.asyncio
async def test_retry_predicate():
    calls = {"count": 0}

    def should_retry(exc):
        return "retry" in str(exc)

    async def fn():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("retry me")
        if calls["count"] == 2:
            raise RuntimeError("stop here")
        return "ok"

    policy = RetryPolicy(max_attempts=3, retry_on=should_retry, backoff=constant_backoff(0))

    with pytest.raises(RetryError):
        await policy.run(fn)
    assert calls["count"] == 2  # stopped after non-retriable


def test_backoff_helpers():
    assert constant_backoff(0.5)(3) == 0.5
    assert linear_backoff(0.2)(3) == pytest.approx(0.6)
@pytest.mark.asyncio
async def test_timeout_policy_success():
    policy = TimeoutPolicy(timeout_seconds=1.0)

    async def fn():
        await asyncio.sleep(0.1)
        return "done"

    result = await policy.run(fn)
    assert result == "done"

    policy.shutdown()


@pytest.mark.asyncio
async def test_timeout_policy_timeout():
    policy = TimeoutPolicy(timeout_seconds=0.1)

    async def fn():
        await asyncio.sleep(0.3)
        return "done"

    with pytest.raises(TimeoutError):
        await policy.run(fn)

    policy.shutdown()


@pytest.mark.asyncio
async def test_circuit_breaker_trip_and_recover(monkeypatch):
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.2, half_open_max_calls=1)

    calls = {"count": 0}

    async def failing():
        calls["count"] += 1
        raise RuntimeError("fail")

    async def success():
        calls["count"] += 1
        return "ok"

    # Two failures -> open
    with pytest.raises(RuntimeError):
        await cb.call(failing)
    with pytest.raises(RuntimeError):
        await cb.call(failing)

    assert cb.state == CircuitBreakerState.OPEN

    # Further calls blocked
    with pytest.raises(CircuitOpenError):
        await cb.call(success)

    # Wait for recovery window
    await asyncio.sleep(0.25)

    # Half-open trial
    result = await cb.call(success)
    assert result == "ok"
    assert cb.state == CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, half_open_max_calls=1)

    async def fail():
        raise RuntimeError("fail")

    # Trip to open
    with pytest.raises(RuntimeError):
        await cb.call(fail)

    assert cb.state == CircuitBreakerState.OPEN

    await asyncio.sleep(0.12)

    # Half-open trial fails -> back to open
    with pytest.raises(RuntimeError):
        await cb.call(fail)

    assert cb.state == CircuitBreakerState.OPEN

    assert cb.state == CircuitBreakerState.OPEN
