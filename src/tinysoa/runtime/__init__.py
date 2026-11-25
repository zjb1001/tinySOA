"""Runtime container, lifecycle management, and dependency resolution."""

from .container import Container
from .coordinator import DependencyCoordinator
from .dependency import DependencyResolver
from .internal_events import (
    InternalEvent,
    InternalEventDispatcher,
    InternalEventType,
    InternalSubscription,
)
from .lifecycle import (
    DefaultHealthChecker,
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    LifecycleHook,
    LifecycleManager,
)
from .proxy import ServiceProxy, ServiceProxyConfig

__all__ = [
    "Container",
    "DefaultHealthChecker",
    "DependencyCoordinator",
    "DependencyResolver",
    "HealthChecker",
    "HealthCheckResult",
    "HealthStatus",
    "InternalEvent",
    "InternalEventDispatcher",
    "InternalEventType",
    "InternalSubscription",
    "LifecycleHook",
    "LifecycleManager",
    "ServiceProxy",
    "ServiceProxyConfig",
]
