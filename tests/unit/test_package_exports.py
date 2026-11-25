"""Public package facades re-export their documented names."""

from __future__ import annotations

import tinysoa.api as api
import tinysoa.core as core
import tinysoa.obs as obs
import tinysoa.runtime as runtime
import tinysoa.spi as spi


def test_runtime_facade_exports() -> None:
    assert runtime.Container is not None
    assert runtime.DependencyResolver is not None
    assert runtime.LifecycleManager is not None
    assert runtime.HealthStatus is not None


def test_core_facade_exports() -> None:
    assert core.Service is not None
    assert core.ServiceDependency is not None
    assert core.DependencyError is not None


def test_api_facade_exports() -> None:
    assert api.ServiceRegistry is not None
    assert api.ServiceInvoker is not None
    assert api.EventPublisher is not None
    assert api.EventSubscriber is not None


def test_spi_facade_exports_interceptors() -> None:
    from tinysoa.spi.interceptor import Interceptor as DirectInterceptor

    assert spi.Interceptor is DirectInterceptor
    assert spi.Plugin is not None


def test_obs_facade_exports_metrics_and_tracing() -> None:
    from tinysoa.obs.metrics import MetricsCollector as DirectCollector

    assert obs.MetricsCollector is DirectCollector
    assert obs.TracingInterceptor is not None
