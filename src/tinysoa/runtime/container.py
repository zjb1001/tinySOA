from __future__ import annotations

from typing import Dict, Optional, Set
from tinysoa.core.model import Service, ServiceStatus
from tinysoa.core.errors import NotFoundError, DuplicateError, StateError


class Container:
    """Service container managing service instances and their dependencies.
    
    Provides registration, lookup, and basic dependency awareness.
    """

    def __init__(self):
        self._services: Dict[int, Service] = {}
        self._name_index: Dict[str, Set[int]] = {}

    def add_service(self, service: Service) -> None:
        """Add a service to the container. Must be unique by id."""
        if service.id in self._services:
            raise DuplicateError(f"Service id {service.id} already exists")
        
        self._services[service.id] = service
        self._name_index.setdefault(service.name, set()).add(service.id)

    def remove_service(self, service_id: int) -> None:
        """Remove a service from the container."""
        service = self._services.pop(service_id, None)
        if service:
            self._name_index.get(service.name, set()).discard(service_id)

    def get_service(self, service_id: int) -> Optional[Service]:
        """Get a service by id, or None if not found."""
        return self._services.get(service_id)

    def find_by_name(self, name: str) -> list[Service]:
        """Find all services with the given name (may be multiple versions)."""
        ids = self._name_index.get(name, set())
        return [self._services[sid] for sid in ids]

    def list_services(self) -> list[Service]:
        """List all services in the container."""
        return list(self._services.values())

    def get_running_services(self) -> list[Service]:
        """Get all services in RUNNING state."""
        return [s for s in self._services.values() if s.status == ServiceStatus.RUNNING]

    def clear(self) -> None:
        """Remove all services from the container."""
        self._services.clear()
        self._name_index.clear()
