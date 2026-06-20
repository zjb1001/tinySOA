from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, Optional, Union, Any

from tinysoa.core.model import Service, Method, Message

ServiceSelector = Union[int, str, Service]
MethodSelector = Union[int, str, Method]


class ServiceRegistry(ABC):
    """Registry interface for service discovery and lifecycle awareness.

    Implementations may provide in-memory, file-backed, or network-based registries.
    """

    @abstractmethod
    def register(self, service: Service) -> None:
        """Register a service instance. Must ensure uniqueness by service id.
        Raises on duplicates.
        """

    @abstractmethod
    def deregister(self, service_id: int) -> None:
        """Remove a service by id. No-op if not present (or raise, per policy)."""

    @abstractmethod
    def find_by_id(self, service_id: int) -> Optional[Service]:
        """Find a service by id, or None if not found."""

    @abstractmethod
    def find_by_name(self, name: str) -> Iterable[Service]:
        """Find services by name (may be multiple versions)."""

    @abstractmethod
    def list_services(self) -> Iterable[Service]:
        """List all registered services."""


class ServiceInvoker(ABC):
    """Invoker interface for calling a service method.

    Implementations decide transport, encoding, timeout and retry semantics.
    """

    @abstractmethod
    async def invoke(
        self,
        service: ServiceSelector,
        method: MethodSelector,
        payload: Any | Message,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Message:
        """Invoke a method and return a Message as response.

        - service: id/name/Service
        - method: id/name/Method
        - payload: raw payload or Message (implementations should wrap raw payload)
        - headers: optional request headers
        - timeout: optional timeout in seconds
        """
        raise NotImplementedError
