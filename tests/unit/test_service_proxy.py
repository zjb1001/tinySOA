"""ServiceProxy: interceptor + retry/timeout/circuit-breaker composition."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional

import pytest

from tinysoa.api.service_api import MethodSelector, ServiceInvoker, ServiceSelector
from tinysoa.core.errors import NotFoundError, StateError, ValidationError
from tinysoa.core.model import Message, Method, Service
from tinysoa.policies.circuit_breaker import CircuitOpenError
from tinysoa.policies.retry import RetryError
from tinysoa.policies.timeout import TimeoutError
from tinysoa.runtime import ServiceProxy, ServiceProxyConfig
from tinysoa.spi.interceptor import Interceptor, InvocationContext, Invoker

SERVICE = Service(
    name="calc",
    id=0x1234,
    version="1.0.0",
    methods=[Method("add", 0x0001), Method("mul", 0x0002)],
)


class FakeInvoker(ServiceInvoker):
    """Record calls and return queued results or raise queued exceptions."""

    def __init__(self, *results: Any) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def invoke(
        self,
        service: ServiceSelector,
        method: MethodSelector,
        payload: Any | Message,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Message:
        self.calls.append(
            {
                "service": service,
                "method": method,
                "payload": payload,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if not self.results:
            return Message(payload={"ok": True})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return await result()
        return result


class ShortCircuit(Interceptor):
    async def intercept(
        self, context: InvocationContext, next_invoker: Invoker
    ) -> None:
        context.set_response(Message(payload={"cached": True}))


class Reject(Interceptor):
    async def intercept(
        self, context: InvocationContext, next_invoker: Invoker
    ) -> None:
        context.set_error(PermissionError("denied"))


class Noop(Interceptor):
    async def intercept(
        self, context: InvocationContext, next_invoker: Invoker
    ) -> None:
        return None


class Recording(Interceptor):
    def __init__(self, name: str, priority: int, events: list[str]) -> None:
        self.name = name
        self._priority = priority
        self._events = events

    @property
    def priority(self) -> int:
        return self._priority

    async def intercept(
        self, context: InvocationContext, next_invoker: Invoker
    ) -> None:
        self._events.append(f"{self.name}:before")
        await next_invoker(context)
        self._events.append(f"{self.name}:after")


async def test_proxy_passes_resolved_method_and_request() -> None:
    invoker = FakeInvoker(Message(payload={"sum": 3}))
    proxy = ServiceProxy(SERVICE, invoker)
    request = Message(payload={"a": 1, "b": 2}, headers={"x-id": "1"})

    response = await proxy.call("add", request, headers={"x-extra": "2"}, timeout=0.5)

    assert response.payload == {"sum": 3}
    call = invoker.calls[0]
    assert call["service"] == SERVICE.id
    assert call["method"].name == "add"
    assert call["payload"].payload == {"a": 1, "b": 2}
    assert call["payload"].headers == {"x-id": "1", "x-extra": "2"}
    assert call["headers"] == {"x-id": "1", "x-extra": "2"}
    assert call["timeout"] == 0.5


async def test_proxy_accepts_method_id_and_model() -> None:
    invoker = FakeInvoker(Message(payload=1), Message(payload=2))
    proxy = ServiceProxy(SERVICE, invoker)

    await proxy.call(0x0001, {"a": 1})
    await proxy.call(Method("mul", 0x0002), {"a": 2})

    assert [call["method"].id for call in invoker.calls] == [0x0001, 0x0002]


async def test_proxy_rejects_unknown_method() -> None:
    proxy = ServiceProxy(SERVICE, FakeInvoker())

    with pytest.raises(NotFoundError):
        await proxy.call("sin", {})
    with pytest.raises(NotFoundError):
        await proxy.call(0x9999, {})
    with pytest.raises(ValidationError):
        await proxy.call(object(), {})  # type: ignore[arg-type]


async def test_proxy_retries_until_success() -> None:
    invoker = FakeInvoker(
        RuntimeError("first"),
        RuntimeError("second"),
        Message(payload={"ok": True}),
    )
    proxy = ServiceProxy(
        SERVICE,
        invoker,
        ServiceProxyConfig(max_attempts=3, retry_backoff=lambda _: 0),
    )

    response = await proxy.call("add", {})

    assert response.payload == {"ok": True}
    assert len(invoker.calls) == 3


async def test_proxy_retry_exhausted_raises_retry_error() -> None:
    invoker = FakeInvoker(RuntimeError("first"), RuntimeError("second"))
    proxy = ServiceProxy(
        SERVICE,
        invoker,
        ServiceProxyConfig(max_attempts=2, retry_backoff=lambda _: 0),
    )

    with pytest.raises(RetryError) as exc_info:
        await proxy.call("add", {})

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert len(invoker.calls) == 2


async def test_proxy_timeout_is_per_attempt() -> None:
    async def slow() -> Message:
        await asyncio.sleep(0.2)
        return Message(payload={"late": True})

    proxy = ServiceProxy(
        SERVICE,
        FakeInvoker(slow),
        ServiceProxyConfig(timeout=0.02),
    )

    with pytest.raises(TimeoutError):
        await proxy.call("add", {})


async def test_proxy_circuit_breaker_opens_and_short_circuits() -> None:
    invoker = FakeInvoker(RuntimeError("boom"))
    proxy = ServiceProxy(
        SERVICE,
        invoker,
        ServiceProxyConfig(failure_threshold=1, recovery_timeout=60.0),
    )

    with pytest.raises(RuntimeError):
        await proxy.call("add", {})
    with pytest.raises(CircuitOpenError):
        await proxy.call("add", {})

    assert len(invoker.calls) == 1


async def test_proxy_interceptor_can_short_circuit() -> None:
    invoker = FakeInvoker()
    proxy = ServiceProxy(
        SERVICE,
        invoker,
        ServiceProxyConfig(interceptors=(ShortCircuit(),)),
    )

    response = await proxy.call("add", {})

    assert response.payload == {"cached": True}
    assert invoker.calls == []


async def test_proxy_interceptor_runs_in_priority_order() -> None:
    events: list[str] = []
    first = Recording("first", 10, events)
    second = Recording("second", 20, events)
    proxy = ServiceProxy(
        SERVICE,
        FakeInvoker(Message(payload={"ok": True})),
        ServiceProxyConfig(interceptors=(second, first)),
    )

    await proxy.call("add", {})

    assert events == [
        "first:before",
        "second:before",
        "second:after",
        "first:after",
    ]


async def test_proxy_propagates_interceptor_error() -> None:
    proxy = ServiceProxy(
        SERVICE,
        FakeInvoker(),
        ServiceProxyConfig(interceptors=(Reject(),)),
    )

    with pytest.raises(PermissionError, match="denied"):
        await proxy.call("add", {})


async def test_proxy_requires_response_or_error() -> None:
    proxy = ServiceProxy(
        SERVICE,
        FakeInvoker(),
        ServiceProxyConfig(interceptors=(Noop(),)),
    )

    with pytest.raises(StateError):
        await proxy.call("add", {})


async def test_proxy_call_timeout_overrides_config() -> None:
    invoker = FakeInvoker(Message(payload={"ok": True}))
    proxy = ServiceProxy(SERVICE, invoker, ServiceProxyConfig(timeout=1.0))

    await proxy.call("add", {}, timeout=0.25)

    assert invoker.calls[0]["timeout"] == 0.25


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"timeout": 0},
        {"failure_threshold": 0},
        {"recovery_timeout": 0},
        {"half_open_max_calls": 0},
    ],
)
def test_proxy_config_validation(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ServiceProxyConfig(**kwargs)


def test_proxy_config_normalizes_interceptors() -> None:
    config = ServiceProxyConfig(interceptors=[ShortCircuit()])  # type: ignore[arg-type]

    assert isinstance(config.interceptors, tuple)
