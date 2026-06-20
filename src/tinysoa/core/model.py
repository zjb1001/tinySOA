from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from .errors import ValidationError, StateError, DuplicateError


class Protocol(str, Enum):
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    HTTPS = "https"


class ServiceStatus(str, Enum):
    INIT = "init"
    REGISTERED = "registered"
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"


_ALLOWED_TRANSITIONS: Mapping[ServiceStatus, List[ServiceStatus]] = {
    ServiceStatus.INIT: [ServiceStatus.REGISTERED],
    ServiceStatus.REGISTERED: [ServiceStatus.RUNNING, ServiceStatus.TERMINATED],
    ServiceStatus.RUNNING: [ServiceStatus.STOPPED, ServiceStatus.TERMINATED],
    ServiceStatus.STOPPED: [ServiceStatus.RUNNING, ServiceStatus.TERMINATED],
    ServiceStatus.TERMINATED: [],
}


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    protocol: Protocol = Protocol.TCP

    def __post_init__(self):
        if not self.host:
            raise ValidationError("Endpoint.host must be non-empty")
        if not (0 < self.port < 65536):
            raise ValidationError("Endpoint.port must be in 1..65535")


@dataclass(frozen=True)
class Method:
    name: str
    id: int
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.name:
            raise ValidationError("Method.name must be non-empty")
        if self.id < 0:
            raise ValidationError("Method.id must be >= 0")


@dataclass(frozen=True)
class Event:
    name: str
    id: int
    payload_schema: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.name:
            raise ValidationError("Event.name must be non-empty")
        if self.id < 0:
            raise ValidationError("Event.id must be >= 0")


@dataclass(frozen=True)
class Message:
    payload: Any
    content_type: str = "application/json"
    correlation_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class Service:
    name: str
    id: int
    version: str
    methods: List[Method] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)
    endpoints: List[Endpoint] = field(default_factory=list)
    status: ServiceStatus = ServiceStatus.INIT

    def __post_init__(self):
        if not self.name:
            raise ValidationError("Service.name must be non-empty")
        if self.id < 0:
            raise ValidationError("Service.id must be >= 0")
        self._validate_uniqueness()

    def _validate_uniqueness(self) -> None:
        names = [m.name for m in self.methods]
        if len(names) != len(set(names)):
            raise DuplicateError("Method names must be unique within a service")
        ids = [m.id for m in self.methods]
        if len(ids) != len(set(ids)):
            raise DuplicateError("Method ids must be unique within a service")

        enames = [e.name for e in self.events]
        if len(enames) != len(set(enames)):
            raise DuplicateError("Event names must be unique within a service")
        eids = [e.id for e in self.events]
        if len(eids) != len(set(eids)):
            raise DuplicateError("Event ids must be unique within a service")

    def can_transition(self, to: ServiceStatus) -> bool:
        return to in _ALLOWED_TRANSITIONS[self.status]

    def transition(self, to: ServiceStatus) -> None:
        if not self.can_transition(to):
            raise StateError(f"Invalid transition: {self.status} -> {to}")
        self.status = to

    def register(self) -> None:
        self.transition(ServiceStatus.REGISTERED)

    def start(self) -> None:
        # allow start from REGISTERED or STOPPED
        if self.status == ServiceStatus.REGISTERED:
            self.transition(ServiceStatus.RUNNING)
        elif self.status == ServiceStatus.STOPPED:
            self.transition(ServiceStatus.RUNNING)
        else:
            raise StateError(f"Cannot start from {self.status}")

    def stop(self) -> None:
        if self.status != ServiceStatus.RUNNING:
            raise StateError("Can only stop from RUNNING")
        self.transition(ServiceStatus.STOPPED)

    def terminate(self) -> None:
        if self.status == ServiceStatus.TERMINATED:
            return
        # allow terminate from any non-terminated state except INIT
        if self.status == ServiceStatus.INIT:
            # require at least registration before terminate for clarity
            self.transition(ServiceStatus.REGISTERED)
        self.transition(ServiceStatus.TERMINATED)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["endpoints"] = [
            {"host": ep.host, "port": ep.port, "protocol": ep.protocol.value}
            for ep in self.endpoints
        ]
        d["methods"] = [asdict(m) for m in self.methods]
        d["events"] = [asdict(e) for e in self.events]
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Service":
        endpoints = [
            Endpoint(
                host=ep["host"],
                port=int(ep["port"]),
                protocol=Protocol(ep.get("protocol", Protocol.TCP.value)),
            )
            for ep in data.get("endpoints", [])
        ]
        methods = [Method(**m) for m in data.get("methods", [])]
        events = [Event(**e) for e in data.get("events", [])]
        status = ServiceStatus(data.get("status", ServiceStatus.INIT.value))
        return cls(
            name=data["name"],
            id=int(data["id"]),
            version=data.get("version", "0.0.0"),
            methods=methods,
            events=events,
            endpoints=endpoints,
            status=status,
        )
