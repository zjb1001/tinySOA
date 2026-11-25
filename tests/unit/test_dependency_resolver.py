"""DependencyResolver and dependency-aware lifecycle ordering."""

from __future__ import annotations

import pytest

from tinysoa.core.errors import (
    DependencyError,
    DuplicateError,
    NotFoundError,
    ValidationError,
)
from tinysoa.core.model import Service, ServiceDependency
from tinysoa.runtime import Container, DependencyResolver, LifecycleManager


def _service(
    name: str,
    service_id: int,
    *dependencies: int,
    required: bool = True,
) -> Service:
    return Service(
        name=name,
        id=service_id,
        version="1.0.0",
        dependencies=[
            ServiceDependency(dependency, required=required)
            for dependency in dependencies
        ],
    )


def _graph() -> Container:
    container = Container()
    for service in (
        _service("engine", 0x1000),
        _service("transmission", 0x2000, 0x1000),
        _service("dashboard", 0x3000, 0x1000, 0x2000),
        _service("diagnostics", 0x4000),
    ):
        container.add_service(service)
    return container


def test_startup_order_puts_dependencies_first() -> None:
    resolver = DependencyResolver(_graph())
    assert resolver.startup_order() == [0x1000, 0x2000, 0x3000, 0x4000]


def test_shutdown_order_is_reverse_startup() -> None:
    resolver = DependencyResolver(_graph())
    assert resolver.shutdown_order() == [0x4000, 0x3000, 0x2000, 0x1000]


def test_startup_layers_group_independent_services() -> None:
    resolver = DependencyResolver(_graph())
    assert resolver.startup_layers() == [[0x1000, 0x4000], [0x2000], [0x3000]]


def test_shutdown_layers_reverse() -> None:
    resolver = DependencyResolver(_graph())
    assert resolver.shutdown_layers() == [[0x3000], [0x2000], [0x4000, 0x1000]]


def test_dependents_and_dependencies() -> None:
    resolver = DependencyResolver(_graph())
    assert resolver.dependencies_of(0x3000) == [0x1000, 0x2000]
    assert resolver.dependencies_of(0x3000, local_only=False) == [0x1000, 0x2000]
    assert resolver.dependents_of(0x1000) == [0x2000, 0x3000]
    assert resolver.dependents_of(0x4000) == []


def test_missing_dependency_is_ignored_by_default() -> None:
    container = Container()
    container.add_service(_service("dashboard", 0x3000, 0x9999))
    resolver = DependencyResolver(container)

    assert resolver.startup_order() == [0x3000]
    assert resolver.missing_required() == {0x3000: [0x9999]}


def test_strict_missing_required_dependency_raises() -> None:
    container = Container()
    container.add_service(_service("dashboard", 0x3000, 0x9999))
    resolver = DependencyResolver(container, strict=True)

    with pytest.raises(DependencyError, match="unregistered dependency"):
        resolver.startup_order()


def test_optional_missing_dependency_is_not_reported() -> None:
    container = Container()
    container.add_service(_service("dashboard", 0x3000, 0x9999, required=False))
    resolver = DependencyResolver(container)

    assert resolver.missing_required() == {}


def test_cycle_detection() -> None:
    container = Container()
    container.add_service(_service("a", 1, 2))
    container.add_service(_service("b", 2, 1))
    resolver = DependencyResolver(container)

    with pytest.raises(DependencyError, match="dependency cycle"):
        resolver.startup_order()
    with pytest.raises(DependencyError, match="dependency cycle"):
        resolver.startup_layers()


def test_unknown_service_dependency_query_raises() -> None:
    resolver = DependencyResolver(_graph())
    with pytest.raises(NotFoundError):
        resolver.dependencies_of(0x9999)


def test_service_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError, match="itself"):
        _service("self", 1, 1)


def test_service_rejects_duplicate_dependencies() -> None:
    with pytest.raises(DuplicateError):
        _service("duplicate", 1, 2, 2)


def test_service_dependency_validation() -> None:
    with pytest.raises(ValidationError):
        ServiceDependency(-1)
    with pytest.raises(ValidationError):
        ServiceDependency(1, timeout_s=0)
    with pytest.raises(ValidationError):
        ServiceDependency(1, required="yes")  # type: ignore[arg-type]


def test_service_dependency_serialization_roundtrip() -> None:
    service = _service("dashboard", 0x3000, 0x1000, 0x2000)
    clone = Service.from_dict(service.to_dict())

    assert clone.dependencies == service.dependencies


def test_lifecycle_start_all_uses_dependency_order() -> None:
    container = _graph()
    manager = LifecycleManager(container)
    started: list[int] = []
    manager.add_on_start_hook(lambda service: started.append(service.id))

    manager.start_all()

    assert started == [0x1000, 0x2000, 0x3000, 0x4000]


def test_lifecycle_stop_all_uses_reverse_dependency_order() -> None:
    container = _graph()
    manager = LifecycleManager(container)
    manager.start_all()
    stopped: list[int] = []
    manager.add_on_stop_hook(lambda service: stopped.append(service.id))

    manager.stop_all()

    assert stopped == [0x4000, 0x3000, 0x2000, 0x1000]


def test_lifecycle_terminate_all_uses_reverse_dependency_order() -> None:
    container = _graph()
    manager = LifecycleManager(container)
    manager.start_all()
    terminated: list[int] = []
    manager.add_on_terminate_hook(lambda service: terminated.append(service.id))

    manager.terminate_all()

    assert terminated == [0x4000, 0x3000, 0x2000, 0x1000]


def test_strict_lifecycle_rejects_starting_before_dependency() -> None:
    container = _graph()
    manager = LifecycleManager(container, strict_dependencies=True)

    with pytest.raises(DependencyError, match="RUNNING"):
        manager.start_service(0x3000)


def test_strict_lifecycle_start_all_succeeds() -> None:
    container = _graph()
    manager = LifecycleManager(container, strict_dependencies=True)

    manager.start_all()

    assert all(
        service.status.value == "running" for service in container.list_services()
    )


def test_start_all_rejects_terminated_required_dependency() -> None:
    container = Container()
    engine = _service("engine", 0x1000)
    dashboard = _service("dashboard", 0x3000, 0x1000)
    container.add_service(engine)
    container.add_service(dashboard)

    engine.register()
    engine.start()
    engine.terminate()

    manager = LifecycleManager(container)
    with pytest.raises(DependencyError, match="RUNNING"):
        manager.start_all()
