import pytest

from tinysoa.core.model import (
    Service,
    Method,
    Event,
    Endpoint,
    Protocol,
    ServiceStatus,
)
from tinysoa.core.errors import DuplicateError, ValidationError, StateError


def test_endpoint_validation():
    with pytest.raises(ValidationError):
        Endpoint(host="", port=8080)
    with pytest.raises(ValidationError):
        Endpoint(host="localhost", port=70000)
    ep = Endpoint(host="127.0.0.1", port=8080, protocol=Protocol.HTTP)
    assert ep.protocol is Protocol.HTTP


def test_service_unique_methods_and_events():
    methods = [Method(name="m1", id=1), Method(name="m2", id=2)]
    events = [Event(name="e1", id=1), Event(name="e2", id=2)]
    svc = Service(name="echo", id=10, version="1.0.0", methods=methods, events=events)
    assert svc.name == "echo"

    with pytest.raises(DuplicateError):
        Service(name="dup", id=11, version="1.0.0", methods=[Method("m", 1), Method("m", 2)])
    with pytest.raises(DuplicateError):
        Service(name="dup", id=12, version="1.0.0", methods=[Method("m1", 1), Method("m2", 1)])
    with pytest.raises(DuplicateError):
        Service(name="dup", id=13, version="1.0.0", events=[Event("e", 1), Event("e", 2)])
    with pytest.raises(DuplicateError):
        Service(name="dup", id=14, version="1.0.0", events=[Event("e1", 1), Event("e2", 1)])


def test_service_status_transitions():
    svc = Service(name="echo", id=1, version="1.0.0")
    assert svc.status is ServiceStatus.INIT

    # must register before running
    with pytest.raises(StateError):
        svc.start()

    svc.register()
    assert svc.status is ServiceStatus.REGISTERED

    svc.start()
    assert svc.status is ServiceStatus.RUNNING

    svc.stop()
    assert svc.status is ServiceStatus.STOPPED

    svc.start()
    assert svc.status is ServiceStatus.RUNNING

    svc.terminate()
    assert svc.status is ServiceStatus.TERMINATED

    # idempotent terminate
    svc.terminate()
    assert svc.status is ServiceStatus.TERMINATED


# ------------------------------------------------------------------ FSM completeness


@pytest.mark.parametrize("from_status,action,to_status", [
    (ServiceStatus.INIT,       "register",   ServiceStatus.REGISTERED),
    (ServiceStatus.REGISTERED, "start",      ServiceStatus.RUNNING),
    (ServiceStatus.RUNNING,    "stop",       ServiceStatus.STOPPED),
    (ServiceStatus.STOPPED,    "start",      ServiceStatus.RUNNING),
    (ServiceStatus.RUNNING,    "terminate",  ServiceStatus.TERMINATED),
    (ServiceStatus.REGISTERED, "terminate",  ServiceStatus.TERMINATED),
    (ServiceStatus.STOPPED,    "terminate",  ServiceStatus.TERMINATED),
    (ServiceStatus.INIT,       "terminate",  ServiceStatus.TERMINATED),
    (ServiceStatus.TERMINATED, "terminate",  ServiceStatus.TERMINATED),
])
def test_all_legal_fsm_transitions(from_status, action, to_status):
    svc = Service(name="fsm", id=1, version="1.0.0")
    svc.status = from_status
    getattr(svc, action)()
    assert svc.status is to_status


@pytest.mark.parametrize("from_status,action", [
    (ServiceStatus.INIT,       "stop"),
    (ServiceStatus.INIT,       "start"),
    (ServiceStatus.REGISTERED, "register"),
    (ServiceStatus.RUNNING,    "register"),
    (ServiceStatus.RUNNING,    "start"),
    (ServiceStatus.STOPPED,    "stop"),
    (ServiceStatus.STOPPED,    "register"),
    (ServiceStatus.TERMINATED, "start"),
    (ServiceStatus.TERMINATED, "stop"),
    (ServiceStatus.TERMINATED, "register"),
])
def test_illegal_fsm_transitions_raise_state_error(from_status, action):
    svc = Service(name="fsm", id=2, version="1.0.0")
    svc.status = from_status
    with pytest.raises(StateError):
        getattr(svc, action)()


def test_can_transition_predicate():
    svc = Service(name="fsm", id=3, version="1.0.0")
    assert svc.can_transition(ServiceStatus.REGISTERED) is True
    assert svc.can_transition(ServiceStatus.STOPPED) is False   # INIT -> STOP illegal
    svc.status = ServiceStatus.REGISTERED
    assert svc.can_transition(ServiceStatus.RUNNING) is True


# ------------------------------------------------------------------ serialization


def test_service_serialization_roundtrip():
    svc = Service(
        name="echo",
        id=100,
        version="1.2.3",
        methods=[Method("say", 1)],
        events=[Event("said", 1)],
        endpoints=[Endpoint("localhost", 9000, Protocol.TCP)],
    )

    data = svc.to_dict()
    clone = Service.from_dict(data)

    assert clone.name == svc.name
    assert clone.id == svc.id
    assert clone.version == svc.version
    assert len(clone.methods) == 1
    assert clone.methods[0].name == "say"
    assert len(clone.events) == 1
    assert clone.events[0].name == "said"
    assert len(clone.endpoints) == 1
    assert clone.endpoints[0].host == "localhost"
