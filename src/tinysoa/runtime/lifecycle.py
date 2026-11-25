from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

from tinysoa.core.errors import DependencyError, StateError
from tinysoa.core.model import Service, ServiceStatus
from tinysoa.runtime.container import Container
from tinysoa.runtime.dependency import DependencyResolver
from tinysoa.runtime.internal_events import InternalEvent, InternalEventDispatcher


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    status: HealthStatus
    message: str = ""
    checked_at: Optional[datetime] = None

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
            return HealthCheckResult(
                HealthStatus.UNKNOWN, f"Service in {service.status}"
            )


class LifecycleManager:
    """Manages service lifecycle: start, stop, health checks, and hooks.

    Provides hooks for on_start, on_stop, on_terminate, and health checks.
    """

    def __init__(
        self,
        container: Container,
        health_checker: Optional[HealthChecker] = None,
        *,
        strict_dependencies: bool = False,
        internal_events: Optional[InternalEventDispatcher] = None,
    ):
        self._container = container
        self._health_checker = health_checker or DefaultHealthChecker()
        self._strict_dependencies = strict_dependencies
        self._internal_events = internal_events
        self._resolver = DependencyResolver(container, strict=strict_dependencies)

        self._on_start_hooks: List[LifecycleHook] = []
        self._on_stop_hooks: List[LifecycleHook] = []
        self._on_terminate_hooks: List[LifecycleHook] = []

    @property
    def dependency_resolver(self) -> DependencyResolver:
        """Return the resolver used for ordered startup and shutdown."""
        return self._resolver

    @property
    def internal_events(self) -> Optional[InternalEventDispatcher]:
        """Return the optional control-plane event dispatcher."""
        return self._internal_events

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

        if self._strict_dependencies:
            self._ensure_dependencies(service)

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
        """Start all services in dependency order.

        Dependencies start before dependents.  A dependency cycle raises
        ``DependencyError`` before any service starts.
        """
        for service_id in self._resolver.startup_order():
            service = self._container.get_service(service_id)
            if service is None:
                continue
            if service.status in (
                ServiceStatus.INIT,
                ServiceStatus.REGISTERED,
                ServiceStatus.STOPPED,
            ):
                self._ensure_dependencies(service)
                self.start_service(service_id)

    def stop_all(self) -> None:
        """Stop all running services in reverse dependency order."""
        for service_id in self._resolver.shutdown_order():
            service = self._container.get_service(service_id)
            if service is not None and service.status == ServiceStatus.RUNNING:
                self.stop_service(service_id)

    def terminate_all(self) -> None:
        """Terminate all services in reverse dependency order."""
        for service_id in self._resolver.shutdown_order():
            service = self._container.get_service(service_id)
            if service is not None and service.status != ServiceStatus.TERMINATED:
                self.terminate_service(service_id)

    async def astart_service(self, service_id: int) -> None:
        """Start a service and publish ``SERVICE_READY`` / dependency events."""
        self.start_service(service_id)
        service = self._container.get_service(service_id)
        if service is not None:
            await self._publish_ready(service)

    async def astop_service(self, service_id: int) -> None:
        """Stop a service and publish ``SERVICE_STOPPED`` / dependency events."""
        self.stop_service(service_id)
        service = self._container.get_service(service_id)
        if service is not None:
            await self._publish_stopped(service, terminated=False)

    async def aterminate_service(self, service_id: int) -> None:
        """Terminate a service and publish ``SERVICE_STOPPED``."""
        self.terminate_service(service_id)
        service = self._container.get_service(service_id)
        if service is not None:
            await self._publish_stopped(service, terminated=True)

    async def astart_all(self) -> None:
        """Start all services in dependency order and publish events."""
        for service_id in self._resolver.startup_order():
            service = self._container.get_service(service_id)
            if service is None:
                continue
            if service.status in (
                ServiceStatus.INIT,
                ServiceStatus.REGISTERED,
                ServiceStatus.STOPPED,
            ):
                self._ensure_dependencies(service)
                await self.astart_service(service_id)

    async def astop_all(self) -> None:
        """Stop all running services in reverse dependency order."""
        for service_id in self._resolver.shutdown_order():
            service = self._container.get_service(service_id)
            if service is not None and service.status == ServiceStatus.RUNNING:
                await self.astop_service(service_id)

    async def aterminate_all(self) -> None:
        """Terminate all services in reverse dependency order."""
        for service_id in self._resolver.shutdown_order():
            service = self._container.get_service(service_id)
            if service is not None and service.status != ServiceStatus.TERMINATED:
                await self.aterminate_service(service_id)

    def _ensure_dependencies(self, service: Service) -> None:
        """Reject starting a service before its local required dependencies run.

        Dependencies that are not registered locally are assumed to be remote
        and are validated by service discovery instead.
        """
        for dependency in service.dependencies:
            if not dependency.required:
                continue
            dependency_service = self._container.get_service(dependency.service_id)
            if dependency_service is None:
                continue
            if dependency_service.status != ServiceStatus.RUNNING:
                raise DependencyError(
                    f"service {service.name!r} requires "
                    f"{dependency_service.name!r} ({dependency.service_id:#x}) "
                    f"to be RUNNING, got {dependency_service.status.value}"
                )

    async def _publish_ready(self, service: Service) -> None:
        if self._internal_events is None:
            return
        await self._internal_events.publish(
            InternalEvent.service_ready(service.id, name=service.name)
        )
        for dependent_id in self._resolver.dependents_of(service.id):
            await self._internal_events.publish(
                InternalEvent.dependency_satisfied(
                    dependent_id, service.id, dependency_name=service.name
                )
            )

    async def _publish_stopped(self, service: Service, *, terminated: bool) -> None:
        if self._internal_events is None:
            return
        await self._internal_events.publish(
            InternalEvent.service_stopped(
                service.id, terminated=terminated, name=service.name
            )
        )
        for dependent_id in self._resolver.dependents_of(service.id):
            await self._internal_events.publish(
                InternalEvent.dependency_lost(
                    dependent_id,
                    service.id,
                    required=self._dependency_is_required(dependent_id, service.id),
                    dependency_name=service.name,
                )
            )

    def _dependency_is_required(self, dependent_id: int, dependency_id: int) -> bool:
        dependent = self._container.get_service(dependent_id)
        if dependent is None:
            return True
        for dependency in dependent.dependencies:
            if dependency.service_id == dependency_id:
                return dependency.required
        return True

    def check_health(self, service_id: int) -> HealthCheckResult:
        """Check health of a specific service."""
        service = self._container.get_service(service_id)
        if not service:
            return HealthCheckResult(
                HealthStatus.UNKNOWN, f"Service {service_id} not found"
            )

        return self._health_checker.check(service)

    def check_all_health(self) -> Dict[int, HealthCheckResult]:
        """Check health of all services in container."""
        results = {}
        for service in self._container.list_services():
            results[service.id] = self._health_checker.check(service)
        return results
