from __future__ import annotations

import asyncio
from typing import Callable, Any, Awaitable


class TimeoutError(Exception):
    """Raised when an operation exceeds the allotted time."""


class TimeoutPolicy:
    """Execute awaitables with a timeout using asyncio.wait_for."""

    def __init__(self, timeout_seconds: float):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self.timeout_seconds = timeout_seconds

    async def run(self, func: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await asyncio.wait_for(func(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Operation timed out after {self.timeout_seconds}s") from exc

    def shutdown(self) -> None:
        pass  # No executor to shutdown in asyncio version
