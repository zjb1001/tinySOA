import pytest

from tinysoa.core.model import Service, Method, Event, ServiceStatus
from tinysoa.core.errors import DuplicateError, StateError
from tinysoa.runtime.container import Container
from tinysoa.runtime.lifecycle import (
    LifecycleManager,
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    DefaultHealthChecker,
)


@pytest.fixture
def sample_services():
    svc1 = Service(name="echo", id=1, version="1.0.0", methods=[Method("say", 1)])
    svc2 = Service(name="calc", id=2, version="1.0.0", methods=[Method("add", 1)])
    svc3 = Service(name="echo", id=3, version="2.0.0", methods=[Method("say", 1)])
    return svc1, svc2, svc3


def test_container_add_and_get(sample_services):
    container = Container()
    svc1, svc2, svc3 = sample_services

    container.add_service(svc1)
    container.add_service(svc2)

    assert container.get_service(1) is svc1
    assert container.get_service(2) is svc2
    assert container.get_service(999) is None

    with pytest.raises(DuplicateError):
        container.add_service(svc1)


def test_container_find_by_name(sample_services):
    container = Container()
    svc1, svc2, svc3 = sample_services

    container.add_service(svc1)
    container.add_service(svc2)
    container.add_service(svc3)

    echo_services = container.find_by_name("echo")
    assert len(echo_services) == 2
    assert all(s.name == "echo" for s in echo_services)

    calc_services = container.find_by_name("calc")
    assert len(calc_services) == 1
    assert calc_services[0].id == 2


def test_container_remove_service(sample_services):
    container = Container()
    svc1, svc2, _ = sample_services

    container.add_service(svc1)
    container.add_service(svc2)

    container.remove_service(1)
    assert container.get_service(1) is None
    assert len(container.list_services()) == 1

    # Remove non-existent is safe
    container.remove_service(999)


def test_container_clear(sample_services):
    container = Container()
    for svc in sample_services:
        container.add_service(svc)

    assert len(container.list_services()) == 3
    container.clear()
    assert len(container.list_services()) == 0


def test_lifecycle_manager_start_stop(sample_services):
    container = Container()
    svc1, _, _ = sample_services
    container.add_service(svc1)

    manager = LifecycleManager(container)

    assert svc1.status == ServiceStatus.INIT

    manager.start_service(1)
    assert svc1.status == ServiceStatus.RUNNING

    manager.stop_service(1)
    assert svc1.status == ServiceStatus.STOPPED

    manager.start_service(1)
    assert svc1.status == ServiceStatus.RUNNING


def test_lifecycle_manager_terminate(sample_services):
    container = Container()
    svc1, _, _ = sample_services
    container.add_service(svc1)

    manager = LifecycleManager(container)
    manager.start_service(1)
    assert svc1.status == ServiceStatus.RUNNING

    manager.terminate_service(1)
    assert svc1.status == ServiceStatus.TERMINATED


def test_lifecycle_manager_hooks(sample_services):
    container = Container()
    svc1, _, _ = sample_services
    container.add_service(svc1)

    manager = LifecycleManager(container)

    events = []

    manager.add_on_start_hook(lambda s: events.append(("start", s.id)))
    manager.add_on_stop_hook(lambda s: events.append(("stop", s.id)))
    manager.add_on_terminate_hook(lambda s: events.append(("terminate", s.id)))

    manager.start_service(1)
    assert ("start", 1) in events

    manager.stop_service(1)
    assert ("stop", 1) in events

    manager.terminate_service(1)
    assert ("terminate", 1) in events


def test_lifecycle_manager_start_all(sample_services):
    container = Container()
    for svc in sample_services:
        container.add_service(svc)

    manager = LifecycleManager(container)
    manager.start_all()

    running = container.get_running_services()
    assert len(running) == 3
    assert all(s.status == ServiceStatus.RUNNING for s in running)


def test_lifecycle_manager_stop_all(sample_services):
    container = Container()
    for svc in sample_services:
        container.add_service(svc)

    manager = LifecycleManager(container)
    manager.start_all()

    manager.stop_all()
    running = container.get_running_services()
    assert len(running) == 0


def test_lifecycle_manager_terminate_all(sample_services):
    container = Container()
    for svc in sample_services:
        container.add_service(svc)

    manager = LifecycleManager(container)
    manager.start_all()
    manager.terminate_all()

    all_services = container.list_services()
    assert all(s.status == ServiceStatus.TERMINATED for s in all_services)


def test_health_checker_default(sample_services):
    checker = DefaultHealthChecker()
    svc1, _, _ = sample_services

    # INIT
    result = checker.check(svc1)
    assert result.status == HealthStatus.UNKNOWN

    # REGISTERED
    svc1.register()
    result = checker.check(svc1)
    assert result.status == HealthStatus.UNKNOWN

    # RUNNING
    svc1.start()
    result = checker.check(svc1)
    assert result.status == HealthStatus.HEALTHY

    # STOPPED
    svc1.stop()
    result = checker.check(svc1)
    assert result.status == HealthStatus.UNHEALTHY

    # TERMINATED
    svc1.terminate()
    result = checker.check(svc1)
    assert result.status == HealthStatus.UNHEALTHY


def test_lifecycle_manager_health_checks(sample_services):
    container = Container()
    svc1, svc2, _ = sample_services
    container.add_service(svc1)
    container.add_service(svc2)

    manager = LifecycleManager(container)
    manager.start_service(1)

    # Check individual service
    result = manager.check_health(1)
    assert result.status == HealthStatus.HEALTHY

    result = manager.check_health(2)
    assert result.status == HealthStatus.UNKNOWN

    # Check all
    all_results = manager.check_all_health()
    assert len(all_results) == 2
    assert all_results[1].status == HealthStatus.HEALTHY
    assert all_results[2].status == HealthStatus.UNKNOWN

    # Non-existent service
    result = manager.check_health(999)
    assert result.status == HealthStatus.UNKNOWN
    assert "not found" in result.message
