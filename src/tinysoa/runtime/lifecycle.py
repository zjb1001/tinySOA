from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

from tinysoa.core.model import Service, ServiceStatus
from tinysoa.core.errors import StateError
from tinysoa.runtime.container import Container


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    status: HealthStatus
    message: str = ""
    checked_at: datetime = None

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.now(timezone.utc)


LifecycleHook = Callable[[Service], None]
HealthCheckHook = Callable[[Service], HealthCheckResult]


class HealthChecker(ABC):
    """Abstract health checker interface."""

    @abstractmethod
    def check(self, service: Service) -> HealthCheckResult:
        """Perform health check on a service."""
        raise NotImplementedError


class DefaultHealthChecker(HealthChecker):
    """Default health checker: service is healthy if RUNNING."""

    def check(self, service: Service) -> HealthCheckResult:
        if service.status == ServiceStatus.RUNNING:
            return HealthCheckResult(HealthStatus.HEALTHY, "Service is running")
        elif service.status == ServiceStatus.STOPPED:
            return HealthCheckResult(HealthStatus.UNHEALTHY, "Service is stopped")
        elif service.status == ServiceStatus.TERMINATED:
            return HealthCheckResult(HealthStatus.UNHEALTHY, "Service is terminated")
        else:
            return HealthCheckResult(HealthStatus.UNKNOWN, f"Service in {service.status}")


class LifecycleManager:
    """Manages service lifecycle: start, stop, health checks, and hooks.
    
    Provides hooks for on_start, on_stop, on_terminate, and health checks.
    """

    def __init__(self, container: Container, health_checker: Optional[HealthChecker] = None):
        self._container = container
        self._health_checker = health_checker or DefaultHealthChecker()
        
        self._on_start_hooks: List[LifecycleHook] = []
        self._on_stop_hooks: List[LifecycleHook] = []
        self._on_terminate_hooks: List[LifecycleHook] = []

    def add_on_start_hook(self, hook: LifecycleHook) -> None:
        """Add a hook to be called after service starts."""
        self._on_start_hooks.append(hook)

    def add_on_stop_hook(self, hook: LifecycleHook) -> None:
        """Add a hook to be called after service stops."""
        self._on_stop_hooks.append(hook)

    def add_on_terminate_hook(self, hook: LifecycleHook) -> None:
        """Add a hook to be called after service terminates."""
        self._on_terminate_hooks.append(hook)

    def start_service(self, service_id: int) -> None:
        """Start a service by id."""
        service = self._container.get_service(service_id)
        if not service:
            raise StateError(f"Service {service_id} not found in container")
        
        # Register if needed
        if service.status == ServiceStatus.INIT:
            service.register()
        
        service.start()
        
        # Run hooks
        for hook in self._on_start_hooks:
            hook(service)

    def stop_service(self, service_id: int) -> None:
        """Stop a running service by id."""
        service = self._container.get_service(service_id)
        if not service:
            raise StateError(f"Service {service_id} not found in container")
        
        service.stop()
        
        # Run hooks
        for hook in self._on_stop_hooks:
            hook(service)

    def terminate_service(self, service_id: int) -> None:
        """Terminate a service by id (graceful shutdown)."""
        service = self._container.get_service(service_id)
        if not service:
            raise StateError(f"Service {service_id} not found in container")
        
        service.terminate()
        
        # Run hooks
        for hook in self._on_terminate_hooks:
            hook(service)

    def start_all(self) -> None:
        """Start all services in the container."""
        for service in self._container.list_services():
            if service.status in (ServiceStatus.INIT, ServiceStatus.REGISTERED, ServiceStatus.STOPPED):
                try:
                    self.start_service(service.id)
                except StateError:
                    # Skip services that can't be started
                    pass

    def stop_all(self) -> None:
        """Stop all running services."""
        for service in self._container.get_running_services():
            try:
                self.stop_service(service.id)
            except StateError:
                pass

    def terminate_all(self) -> None:
        """Gracefully terminate all services."""
        for service in self._container.list_services():
            if service.status != ServiceStatus.TERMINATED:
                try:
                    self.terminate_service(service.id)
                except StateError:
                    pass

    def check_health(self, service_id: int) -> HealthCheckResult:
        """Check health of a specific service."""
        service = self._container.get_service(service_id)
        if not service:
            return HealthCheckResult(
                HealthStatus.UNKNOWN,
                f"Service {service_id} not found"
            )
        
        return self._health_checker.check(service)

    def check_all_health(self) -> Dict[int, HealthCheckResult]:
        """Check health of all services in container."""
        results = {}
        for service in self._container.list_services():
            results[service.id] = self._health_checker.check(service)
        return results
