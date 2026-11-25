"""Observability: metrics collection and tracing."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .metrics import (
        ConsoleMetricsExporter,
        Counter,
        Gauge,
        Histogram,
        Metric,
        MetricsCollector,
        MetricsExporter,
        MetricType,
        get_metrics_collector,
    )
    from .tracing import Span, TracingContext, TracingInterceptor

__all__ = [
    "ConsoleMetricsExporter",
    "Counter",
    "Gauge",
    "Histogram",
    "Metric",
    "MetricsCollector",
    "MetricsExporter",
    "MetricType",
    "Span",
    "TracingContext",
    "TracingInterceptor",
    "get_metrics_collector",
]

_LAZY_IMPORTS = {
    "ConsoleMetricsExporter": (".metrics", "ConsoleMetricsExporter"),
    "Counter": (".metrics", "Counter"),
    "Gauge": (".metrics", "Gauge"),
    "Histogram": (".metrics", "Histogram"),
    "Metric": (".metrics", "Metric"),
    "MetricsCollector": (".metrics", "MetricsCollector"),
    "MetricsExporter": (".metrics", "MetricsExporter"),
    "MetricType": (".metrics", "MetricType"),
    "Span": (".tracing", "Span"),
    "TracingContext": (".tracing", "TracingContext"),
    "TracingInterceptor": (".tracing", "TracingInterceptor"),
    "get_metrics_collector": (".metrics", "get_metrics_collector"),
}


def __getattr__(name: str) -> Any:
    """Resolve public names lazily so tracing and SPI stay import-safe."""
    try:
        module_name, attribute = _LAZY_IMPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = import_module(module_name, __name__)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
