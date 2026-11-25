"""Dependency-aware startup ordering for services in a container."""

from __future__ import annotations

from typing import Dict, List, Optional

from tinysoa.core.errors import DependencyError, NotFoundError
from tinysoa.core.model import Service
from tinysoa.runtime.container import Container


class DependencyResolver:
    """Resolve service startup and shutdown order from declared dependencies.

    Ordering is derived from :attr:`tinysoa.core.model.Service.dependencies`.
    Only services present in the container participate in the topology, so a
    required dependency that is not registered locally is treated as remote and
    ignored unless ``strict`` is set.

    ``startup_layers`` groups services by dependency depth.  Services in the
    same layer have no edges between them and may be started concurrently;
    services in a later layer may only start after every earlier layer.
    """

    def __init__(self, container: Container, *, strict: bool = False) -> None:
        self._container = container
        self._strict = strict

    def startup_layers(self) -> List[List[int]]:
        """Return service ids grouped by dependency depth (dependencies first)."""
        services = self._services()
        graph = self._build_graph(services)
        layers = self._topological_layers(graph)
        if sum(len(layer) for layer in layers) != len(graph):
            cycle = self._find_cycle(graph)
            raise DependencyError(self._cycle_message(cycle, services))
        return layers

    def startup_order(self) -> List[int]:
        """Return a branch-complete startup order (dependencies first).

        Unlike :meth:`startup_layers`, this walks each dependency branch to its
        root before moving to the next branch, so a dependent only appears after
        its whole subtree.  Container insertion order breaks ties.
        """
        services = self._services()
        graph = self._build_graph(services)
        order: List[int] = []
        state = {service_id: 0 for service_id in graph}
        stack: List[int] = []

        def visit(service_id: int) -> None:
            if state[service_id] == 2:
                return
            if state[service_id] == 1:
                cycle = stack[stack.index(service_id) :] + [service_id]
                raise DependencyError(self._cycle_message(cycle, services))
            state[service_id] = 1
            stack.append(service_id)
            for dependency_id in graph[service_id]:
                visit(dependency_id)
            stack.pop()
            state[service_id] = 2
            order.append(service_id)

        for service_id in graph:
            visit(service_id)
        return order

    def shutdown_layers(self) -> List[List[int]]:
        """Return dependency layers in reverse order (dependents first)."""
        return [list(reversed(layer)) for layer in reversed(self.startup_layers())]

    def shutdown_order(self) -> List[int]:
        """Return the exact reverse of :meth:`startup_order`."""
        return list(reversed(self.startup_order()))

    def dependencies_of(self, service_id: int, *, local_only: bool = True) -> List[int]:
        """Return the direct dependency ids declared by ``service_id``."""
        service = self._require_service(service_id)
        dependency_ids = [dependency.service_id for dependency in service.dependencies]
        if local_only:
            local_ids = set(self._services())
            dependency_ids = [
                dependency_id
                for dependency_id in dependency_ids
                if dependency_id in local_ids
            ]
        return dependency_ids

    def dependents_of(self, service_id: int) -> List[int]:
        """Return the ids of local services that directly depend on ``service_id``."""
        dependents: List[int] = []
        for service in self._container.list_services():
            dependency_ids = {
                dependency.service_id for dependency in service.dependencies
            }
            if service_id in dependency_ids:
                dependents.append(service.id)
        return dependents

    def missing_required(self) -> Dict[int, List[int]]:
        """Return required dependency ids that are not registered locally.

        Results are keyed by the dependent service id.  Empty when every
        required dependency is local.
        """
        local_ids = set(self._services())
        missing: Dict[int, List[int]] = {}
        for service in self._container.list_services():
            dependency_ids = [
                dependency.service_id
                for dependency in service.dependencies
                if dependency.required and dependency.service_id not in local_ids
            ]
            if dependency_ids:
                missing[service.id] = dependency_ids
        return missing

    def _services(self) -> Dict[int, Service]:
        return {service.id: service for service in self._container.list_services()}

    def _require_service(self, service_id: int) -> Service:
        service = self._container.get_service(service_id)
        if service is None:
            raise NotFoundError(f"Service {service_id} not found in container")
        return service

    def _build_graph(self, services: Dict[int, Service]) -> Dict[int, List[int]]:
        graph: Dict[int, List[int]] = {}
        for service_id, service in services.items():
            dependency_ids: List[int] = []
            for dependency in service.dependencies:
                if dependency.service_id in services:
                    dependency_ids.append(dependency.service_id)
                elif self._strict and dependency.required:
                    raise DependencyError(
                        f"service {service.name!r} requires unregistered dependency "
                        f"{dependency.service_id:#x}"
                    )
            graph[service_id] = dependency_ids
        return graph

    @staticmethod
    def _topological_layers(graph: Dict[int, List[int]]) -> List[List[int]]:
        indegree = {
            service_id: len(dependency_ids)
            for service_id, dependency_ids in graph.items()
        }
        dependents: Dict[int, List[int]] = {service_id: [] for service_id in graph}
        for service_id, dependency_ids in graph.items():
            for dependency_id in dependency_ids:
                dependents[dependency_id].append(service_id)

        ready = [service_id for service_id in graph if indegree[service_id] == 0]
        layers: List[List[int]] = []
        while ready:
            layers.append(ready)
            next_ready: List[int] = []
            for service_id in ready:
                for dependent_id in dependents[service_id]:
                    indegree[dependent_id] -= 1
                    if indegree[dependent_id] == 0:
                        next_ready.append(dependent_id)
            ready = next_ready
        return layers

    @staticmethod
    def _find_cycle(graph: Dict[int, List[int]]) -> List[int]:
        white, gray, black = 0, 1, 2
        color = {service_id: white for service_id in graph}
        stack: List[int] = []

        def visit(service_id: int) -> Optional[List[int]]:
            color[service_id] = gray
            stack.append(service_id)
            for dependency_id in graph[service_id]:
                if color[dependency_id] == gray:
                    return stack[stack.index(dependency_id) :] + [dependency_id]
                if color[dependency_id] == white:
                    cycle = visit(dependency_id)
                    if cycle is not None:
                        return cycle
            stack.pop()
            color[service_id] = black
            return None

        for service_id in graph:
            if color[service_id] == white:
                cycle = visit(service_id)
                if cycle is not None:
                    return cycle
        return []

    @staticmethod
    def _cycle_message(cycle: List[int], services: Dict[int, Service]) -> str:
        if not cycle:
            return "dependency cycle detected"
        rendered = " -> ".join(
            (
                f"{services[service_id].name}({service_id:#x})"
                if service_id in services
                else f"{service_id:#x}"
            )
            for service_id in cycle
        )
        return f"dependency cycle detected: {rendered}"
