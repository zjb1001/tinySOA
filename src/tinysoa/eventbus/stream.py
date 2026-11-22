from __future__ import annotations

from abc import ABC, abstractmethod


class MessageStream(ABC):
    """A framed byte stream used by broker-based EventBus adapters.

    The interface is deliberately small and asyncio-oriented:

    * ``open`` / ``close`` manage the connection lifecycle.
    * ``write`` is non-blocking, mirroring ``asyncio.StreamWriter.write``.
    * ``drain`` waits until the transport has flushed buffered frames.
    * ``readline`` returns the next frame, or ``b""`` at end-of-stream.

    TCP is the first implementation.  Unix sockets, TLS, or an in-memory pair
    can implement the same contract without changing EventBus semantics.
    """

    @abstractmethod
    async def open(self) -> None:
        """Open the connection; idempotent when already open."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the connection; idempotent when already closed."""
        raise NotImplementedError

    @abstractmethod
    def write(self, frame: bytes) -> None:
        """Buffer one frame without blocking."""
        raise NotImplementedError

    @abstractmethod
    async def drain(self) -> None:
        """Wait for buffered frames to be flushed."""
        raise NotImplementedError

    @abstractmethod
    async def readline(self) -> bytes:
        """Return the next frame, or ``b""`` at end-of-stream."""
        raise NotImplementedError
