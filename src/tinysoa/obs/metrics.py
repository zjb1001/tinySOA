from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
import statistics
from threading import Lock


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class Metric:
    """Base metric data structure."""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Counter:
    """Counter metric - monotonically increasing value."""
    
    def __init__(self, name: str, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.labels = labels or {}
        self._value: float = 0.0
    
    def inc(self, amount: float = 1.0) -> None:
        """Increment the counter by amount."""
        self._value += amount
    
    def get(self) -> float:
        """Get current value."""
        return self._value
    
    def reset(self) -> None:
        """Reset counter to 0."""
        self._value = 0.0
    
    def to_metric(self) -> Metric:
        """Convert to Metric."""
        return Metric(
            name=self.name,
            type=MetricType.COUNTER,
            value=self.get(),
            labels=self.labels,
        )


class Gauge:
    """Gauge metric - value that can go up and down."""
    
    def __init__(self, name: str, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.labels = labels or {}
        self._value: float = 0.0
        self._lock = Lock()
    
    def set(self, value: float) -> None:
        """Set the gauge value."""
        self._value = value
    
    def inc(self, amount: float = 1.0) -> None:
        """Increment the gauge."""
        self._value += amount
    
    def dec(self, amount: float = 1.0) -> None:
        """Decrement the gauge."""
        self._value -= amount
    
    def get(self) -> float:
        """Get current value."""
        return self._value

    def to_metric(self) -> Metric:
        return Metric(
            name=self.name,
            type=MetricType.GAUGE,
            value=self.get(),
            labels=self.labels,
        )


class Histogram:
    """Histogram metric - tracks distribution of values."""
    
    def __init__(self, name: str, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.labels = labels or {}
        self._values: List[float] = []
        self._lock = Lock()
    
    def observe(self, value: float) -> None:
        """Record a value."""
        with self._lock:
            self._values.append(value)
    
    def get_count(self) -> int:
        """Get number of observations."""
        with self._lock:
            return len(self._values)
    
    def get_sum(self) -> float:
        """Get sum of all observations."""
        with self._lock:
            return sum(self._values)
    
    def get_avg(self) -> float:
        """Get average value."""
        with self._lock:
            if not self._values:
                return 0.0
            return statistics.mean(self._values)
    
    def get_percentile(self, percentile: float) -> float:
        """Get percentile (0-100)."""
        with self._lock:
            if not self._values:
                return 0.0
            sorted_values = sorted(self._values)
            index = int(len(sorted_values) * (percentile / 100.0))
            if index >= len(sorted_values):
                index = len(sorted_values) - 1
            return sorted_values[index]
    
    def reset(self) -> None:
        """Clear all observations."""
        with self._lock:
            self._values.clear()
    
    def to_metric(self) -> Metric:
        """Convert to Metric (uses average as value)."""
        return Metric(
            name=self.name,
            type=MetricType.HISTOGRAM,
            value=self.get_avg(),
            labels=self.labels,
        )


class MetricsCollector:
    """Central metrics collector and registry."""
    
    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = Lock()
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key for metric with labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> Counter:
        """Get or create a counter."""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = Counter(name, labels)
            return self._counters[key]
    
    def gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Gauge:
        """Get or create a gauge."""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = Gauge(name, labels)
            return self._gauges[key]
    
    def histogram(self, name: str, labels: Optional[Dict[str, str]] = None) -> Histogram:
        """Get or create a histogram."""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(name, labels)
            return self._histograms[key]
    
    def collect_all(self) -> List[Metric]:
        """Collect all metrics as a list."""
        metrics = []
        
        with self._lock:
            for counter in self._counters.values():
                metrics.append(counter.to_metric())
            for gauge in self._gauges.values():
                metrics.append(gauge.to_metric())
            for histogram in self._histograms.values():
                metrics.append(histogram.to_metric())
        
        return metrics
    
    def reset_all(self) -> None:
        """Reset all metrics."""
        with self._lock:
            for counter in self._counters.values():
                counter.reset()
            for histogram in self._histograms.values():
                histogram.reset()
            # Gauges are not reset as they represent current state
    
    def get_service_metrics(self, service_name: str) -> Dict[str, Any]:
        """Get aggregated metrics for a specific service."""
        metrics = {}
        
        # Find all metrics for this service
        for metric in self.collect_all():
            if metric.labels.get("service") == service_name:
                metrics[metric.name] = metric.value
        
        return metrics


class MetricsExporter(ABC):
    """Interface for exporting metrics to external systems."""
    
    @abstractmethod
    async def export(self, metrics: List[Metric]) -> None:
        """Export a batch of metrics."""
        raise NotImplementedError


class ConsoleMetricsExporter(MetricsExporter):
    """Simple exporter that prints metrics to console."""
    
    async def export(self, metrics: List[Metric]) -> None:
        print(f"--- Metrics Export ({datetime.now(timezone.utc)}) ---")
        for metric in metrics:
            labels = ",".join(f"{k}={v}" for k, v in metric.labels.items())
            print(f"{metric.name}[{labels}]: {metric.value} ({metric.type.value})")
        print("------------------------------------------------")


# Global metrics collector instance
_global_collector: Optional[MetricsCollector] = None



def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector
