from __future__ import annotations

import asyncio
import random
from typing import Callable, Iterable, Optional, Type, Any, Awaitable


class RetryError(Exception):
    """Raised when retry attempts are exhausted."""


class RetryPolicy:
    """Configurable retry policy with backoff and jitter.

    - max_attempts: total attempts including the first
    - backoff: function taking attempt index (1-based) -> seconds sleep
    - retry_on: tuple of exception types to retry, or callable(exc) -> bool
    - jitter: optional callable returning jitter seconds to add/subtract
    """

    def __init__(
        self,
        max_attempts: int = 3,
        backoff: Optional[Callable[[int], float]] = None,
        retry_on: Optional[Iterable[Type[BaseException]]] = (Exception,),
        jitter: Optional[Callable[[], float]] = None,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self.backoff = backoff or (lambda attempt: 0.0)
        self.retry_on = retry_on
        self.jitter = jitter

    def _should_retry(self, exc: BaseException) -> bool:
        if self.retry_on is None:
            return False
        if callable(self.retry_on) and not isinstance(self.retry_on, type):
            return bool(self.retry_on(exc))
        # Assume iterable of exception types
        return isinstance(exc, tuple(self.retry_on))

    async def _sleep(self, attempt: int) -> None:
        delay = self.backoff(attempt)
        if self.jitter:
            delay += self.jitter()
        if delay > 0:
            await asyncio.sleep(delay)

    async def run(self, func: Callable[[], Awaitable[Any]]) -> Any:
        """Run func with retry policy."""
        last_exc = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await func()
            except Exception as exc:  # catch broad, then decide
                last_exc = exc
                if attempt >= self.max_attempts or not self._should_retry(exc):
                    break
                await self._sleep(attempt)
                continue
        raise RetryError(f"Retry attempts exhausted after {self.max_attempts}") from last_exc


# Common backoff helpers

def constant_backoff(seconds: float) -> Callable[[int], float]:
    return lambda attempt: seconds


def linear_backoff(base: float = 0.1) -> Callable[[int], float]:
    return lambda attempt: base * attempt


def exponential_backoff(base: float = 0.1, factor: float = 2.0, max_delay: Optional[float] = None) -> Callable[[int], float]:
    def backoff(attempt: int) -> float:
        delay = base * (factor ** (attempt - 1))
        if max_delay is not None:
            delay = min(delay, max_delay)
        return delay
    return backoff


def full_jitter(max_delay: float = 1.0) -> Callable[[], float]:
    return lambda: random.uniform(0, max_delay)
