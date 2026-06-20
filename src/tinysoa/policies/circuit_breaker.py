from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Any, Optional, Awaitable


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when circuit is open and calls are blocked."""


class CircuitBreaker:
    """Simple circuit breaker implementation.

    - failure_threshold: failures required to open the circuit
    - recovery_timeout: seconds to wait before transitioning to HALF_OPEN
    - half_open_max_calls: allowed trial calls in HALF_OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self._half_open_calls = 0

    def _transition_to_open(self):
        self.state = CircuitBreakerState.OPEN
        self.last_failure_time = time.monotonic()
        self._half_open_calls = 0

    def _transition_to_half_open_if_ready(self):
        if self.state == CircuitBreakerState.OPEN and self.last_failure_time is not None:
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.failure_count = 0
                self._half_open_calls = 0

    def _record_success(self):
        if self.state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls += 1
            # After successful trial calls, close the circuit
            if self._half_open_calls >= self.half_open_max_calls:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self._half_open_calls = 0
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def _record_failure(self):
        self.failure_count += 1
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Immediately open on failure in HALF_OPEN
            self._transition_to_open()
        elif self.state == CircuitBreakerState.CLOSED and self.failure_count >= self.failure_threshold:
            self._transition_to_open()

    async def call(self, func: Callable[[], Awaitable[Any]]) -> Any:
        """Execute func under circuit breaker protection."""
        # Transition from OPEN to HALF_OPEN if enough time passed
        self._transition_to_half_open_if_ready()

        if self.state == CircuitBreakerState.OPEN:
            raise CircuitOpenError("Circuit is open")

        try:
            result = await func()
        except Exception:
            self._record_failure()
            raise
        else:
            self._record_success()
            return result
