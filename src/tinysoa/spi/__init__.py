"""SPI contracts: interceptors and plugins."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .interceptor import (
        AuthInterceptor,
        Interceptor,
        InterceptorChain,
        InvocationContext,
        Invoker,
        LoggingInterceptor,
        MetricsInterceptor,
    )
    from .plugin import Plugin, PluginLifecycle, PluginManager

__all__ = [
    "AuthInterceptor",
    "Interceptor",
    "InterceptorChain",
    "InvocationContext",
    "Invoker",
    "LoggingInterceptor",
    "MetricsInterceptor",
    "Plugin",
    "PluginLifecycle",
    "PluginManager",
]

_LAZY_IMPORTS = {
    "AuthInterceptor": (".interceptor", "AuthInterceptor"),
    "Interceptor": (".interceptor", "Interceptor"),
    "InterceptorChain": (".interceptor", "InterceptorChain"),
    "InvocationContext": (".interceptor", "InvocationContext"),
    "Invoker": (".interceptor", "Invoker"),
    "LoggingInterceptor": (".interceptor", "LoggingInterceptor"),
    "MetricsInterceptor": (".interceptor", "MetricsInterceptor"),
    "Plugin": (".plugin", "Plugin"),
    "PluginLifecycle": (".plugin", "PluginLifecycle"),
    "PluginManager": (".plugin", "PluginManager"),
}


def __getattr__(name: str) -> Any:
    """Resolve public names lazily so interceptor/obs imports stay acyclic."""
    try:
        module_name, attribute = _LAZY_IMPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = import_module(module_name, __name__)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
