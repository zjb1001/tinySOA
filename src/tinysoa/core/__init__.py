"""Core domain model and framework errors."""

from .errors import (
    DependencyError,
    DuplicateError,
    NotFoundError,
    StateError,
    TinySOAError,
    ValidationError,
)
from .model import (
    Endpoint,
    Event,
    Message,
    Method,
    Protocol,
    Service,
    ServiceDependency,
    ServiceStatus,
)

__all__ = [
    "DependencyError",
    "DuplicateError",
    "Endpoint",
    "Event",
    "Message",
    "Method",
    "NotFoundError",
    "Protocol",
    "Service",
    "ServiceDependency",
    "ServiceStatus",
    "StateError",
    "TinySOAError",
    "ValidationError",
]
