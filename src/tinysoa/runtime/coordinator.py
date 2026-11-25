"""Event-driven dependency coordination."""

from __future__ import annotations

import asyncio
from typing import List, Optional, Set

from tinysoa.core.errors import DependencyError, ValidationError
from tinysoa.core.model import Service, ServiceDependency, ServiceStatus
from tinysoa.runtime.container import Container
from tinysoa.runtime.internal_events import (
    InternalEvent,
    InternalEventDispatcher,
    InternalEventType,
    InternalSubscription,
)


class DependencyCoordinator:
    """Wait for a service's required dependencies to become available.

    The coordinator combines two sources of truth:

    - a snapshot of local services that are already ``RUNNING``;
    - ``DEPENDENCY_SATISFIED`` and ``INSTANCE_DISCOVERED`` control-plane events
      for dependencies that are remote or become available later.

    Subscriptions are installed *before* the snapshot so no event can be lost
    between the two steps.  Optional dependencies never block startup.  This is
    a one-shot wait: runtime loss handling belongs to a long-running monitor.

    Start the wait before dependencies may become available.  Dispatcher history
    is not replayed, so a satisfaction event published before this call is only
    observed through the local ``RUNNING`` snapshot.
    """

    def __init__(
        self,
        service: Service,
        container: Container,
        dispatcher: InternalEventDispatcher,
    ) -> None:
        self._service = service
        self._container = container
        self._dispatcher = dispatcher

    @property
    def service(self) -> Service:
        return self._service

    @property
    def required_dependencies(self) -> List[ServiceDependency]:
        return [
            dependency
            for dependency in self._service.dependencies
            if dependency.required
        ]

    async def wait_for_dependencies(self, timeout: Optional[float] = None) -> None:
        """Return once every required dependency is available.

        ``timeout`` overrides the per-dependency ``timeout_s`` values; when it
        is omitted, the largest declared ``timeout_s`` is used.  A timeout or a
        locally ``TERMINATED`` dependency raises :class:`DependencyError`.
        """
        required = self.required_dependencies
        if not required:
            return
        if timeout is not None and timeout <= 0:
            raise ValidationError("DependencyCoordinator.timeout must be positive")

        required_ids = {dependency.service_id for dependency in required}
        satisfied: Set[int] = set()
        done = asyncio.Event()

        async def on_available(event: InternalEvent) -> None:
            dependency_id = event.related_service_id
            if dependency_id is None or dependency_id not in required_ids:
                return
            satisfied.add(dependency_id)
            if required_ids <= satisfied:
                done.set()

        subscriptions: List[InternalSubscription] = [
            self._dispatcher.subscribe(
                InternalEventType.DEPENDENCY_SATISFIED, on_available
            ),
            self._dispatcher.subscribe(
                InternalEventType.INSTANCE_DISCOVERED, on_available
            ),
        ]
        try:
            for dependency in required:
                if self._is_locally_running(dependency.service_id):
                    satisfied.add(dependency.service_id)
                    continue
                local = self._container.get_service(dependency.service_id)
                if local is not None and local.status == ServiceStatus.TERMINATED:
                    raise DependencyError(
                        f"service {self._service.name!r} requires "
                        f"{local.name!r} ({dependency.service_id:#x}) "
                        "which is TERMINATED"
                    )

            if required_ids <= satisfied:
                return

            effective_timeout = timeout
            if effective_timeout is None:
                effective_timeout = max(dependency.timeout_s for dependency in required)
            try:
                await asyncio.wait_for(done.wait(), timeout=effective_timeout)
            except asyncio.TimeoutError:
                missing = required_ids - satisfied
                names = ", ".join(
                    self._describe(dependency_id) for dependency_id in sorted(missing)
                )
                raise DependencyError(
                    f"service {self._service.name!r} timed out waiting for: {names}"
                ) from None
        finally:
            for subscription in subscriptions:
                self._dispatcher.unsubscribe(subscription)

    def _is_locally_running(self, service_id: int) -> bool:
        service = self._container.get_service(service_id)
        return service is not None and service.status == ServiceStatus.RUNNING

    def _describe(self, service_id: int) -> str:
        service = self._container.get_service(service_id)
        if service is None:
            return f"{service_id:#x}"
        return f"{service.name}({service_id:#x})"
