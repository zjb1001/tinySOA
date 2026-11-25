"""DependencyCoordinator: snapshot + control-plane events + timeout."""

from __future__ import annotations

import asyncio

import pytest

from tinysoa.core.errors import DependencyError
from tinysoa.core.model import Service, ServiceDependency
from tinysoa.runtime import (
    Container,
    DependencyCoordinator,
    InternalEvent,
    InternalEventDispatcher,
    LifecycleManager,
)


def _service(
    name: str,
    service_id: int,
    *dependencies: int,
    required: bool = True,
    timeout_s: float = 10.0,
) -> Service:
    return Service(
        name=name,
        id=service_id,
        version="1.0.0",
        dependencies=[
            ServiceDependency(dependency, required=required, timeout_s=timeout_s)
            for dependency in dependencies
        ],
    )


async def test_no_required_dependencies_returns_immediately() -> None:
    service = _service("standalone", 1)
    coordinator = DependencyCoordinator(service, Container(), InternalEventDispatcher())

    await asyncio.wait_for(coordinator.wait_for_dependencies(), timeout=0.1)


async def test_local_running_dependency_is_satisfied_by_snapshot() -> None:
    container = Container()
    engine = _service("engine", 0x1000)
    dashboard = _service("dashboard", 0x3000, 0x1000)
    container.add_service(engine)
    container.add_service(dashboard)
    engine.register()
    engine.start()
    dispatcher = InternalEventDispatcher()

    coordinator = DependencyCoordinator(dashboard, container, dispatcher)

    await asyncio.wait_for(coordinator.wait_for_dependencies(), timeout=0.1)
    assert dispatcher.subscriber_count() == 0


@pytest.mark.parametrize(
    "event_factory",
    [
        lambda: InternalEvent.dependency_satisfied(0x3000, 0x9999),
        lambda: InternalEvent.instance_discovered(0x9999, 1),
    ],
)
async def test_control_plane_event_satisfies_remote_dependency(
    event_factory,
) -> None:
    container = Container()
    dashboard = _service("dashboard", 0x3000, 0x9999)
    container.add_service(dashboard)
    dispatcher = InternalEventDispatcher()
    coordinator = DependencyCoordinator(dashboard, container, dispatcher)
    waiter = asyncio.create_task(coordinator.wait_for_dependencies(timeout=1.0))
    await asyncio.sleep(0.01)

    await dispatcher.publish(event_factory())

    await asyncio.wait_for(waiter, timeout=1.0)
    assert dispatcher.subscriber_count() == 0


async def test_waits_for_all_required_dependencies() -> None:
    container = Container()
    engine = _service("engine", 0x1000)
    dashboard = _service("dashboard", 0x3000, 0x1000, 0x9999)
    container.add_service(engine)
    container.add_service(dashboard)
    engine.register()
    engine.start()
    dispatcher = InternalEventDispatcher()
    coordinator = DependencyCoordinator(dashboard, container, dispatcher)
    waiter = asyncio.create_task(coordinator.wait_for_dependencies(timeout=1.0))
    await asyncio.sleep(0.01)

    assert waiter.done() is False
    await dispatcher.publish(InternalEvent.dependency_satisfied(dashboard.id, 0x9999))

    await asyncio.wait_for(waiter, timeout=1.0)


async def test_timeout_raises_dependency_error_and_unsubscribes() -> None:
    container = Container()
    dashboard = _service("dashboard", 0x3000, 0x9999, timeout_s=0.02)
    container.add_service(dashboard)
    dispatcher = InternalEventDispatcher()
    coordinator = DependencyCoordinator(dashboard, container, dispatcher)

    with pytest.raises(DependencyError, match="timed out"):
        await coordinator.wait_for_dependencies()

    assert dispatcher.subscriber_count() == 0


async def test_optional_dependencies_do_not_block() -> None:
    container = Container()
    dashboard = _service("dashboard", 0x3000, 0x9999, required=False)
    container.add_service(dashboard)
    coordinator = DependencyCoordinator(dashboard, container, InternalEventDispatcher())

    await asyncio.wait_for(coordinator.wait_for_dependencies(timeout=0.1), 0.2)


async def test_terminated_local_dependency_fails_fast() -> None:
    container = Container()
    engine = _service("engine", 0x1000)
    dashboard = _service("dashboard", 0x3000, 0x1000)
    container.add_service(engine)
    container.add_service(dashboard)
    engine.register()
    engine.start()
    engine.terminate()
    dispatcher = InternalEventDispatcher()
    coordinator = DependencyCoordinator(dashboard, container, dispatcher)

    with pytest.raises(DependencyError, match="TERMINATED"):
        await coordinator.wait_for_dependencies()

    assert dispatcher.subscriber_count() == 0


async def test_coordinator_wakes_on_async_lifecycle_events() -> None:
    container = Container()
    engine = _service("engine", 0x1000)
    transmission = _service("transmission", 0x2000, 0x1000)
    dashboard = _service("dashboard", 0x3000, 0x1000, 0x2000)
    for service in (engine, transmission, dashboard):
        container.add_service(service)
    dispatcher = InternalEventDispatcher()
    manager = LifecycleManager(container, internal_events=dispatcher)
    coordinator = DependencyCoordinator(dashboard, container, dispatcher)
    waiter = asyncio.create_task(coordinator.wait_for_dependencies(timeout=1.0))
    await asyncio.sleep(0.01)

    await manager.astart_service(engine.id)
    await manager.astart_service(transmission.id)

    await asyncio.wait_for(waiter, timeout=1.0)
    assert dispatcher.subscriber_count() == 0
