"""Client-side service proxy composing invoker, interceptors, and policies."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping, Optional, Type

from tinysoa.api.service_api import MethodSelector, ServiceInvoker
from tinysoa.core.errors import NotFoundError, StateError, ValidationError
from tinysoa.core.model import Message, Method, Service
from tinysoa.policies.circuit_breaker import CircuitBreaker
from tinysoa.policies.retry import RetryPolicy, constant_backoff
from tinysoa.policies.timeout import TimeoutPolicy
from tinysoa.spi.interceptor import Interceptor, InterceptorChain, InvocationContext

DEFAULT_RETRY_BACKOFF_SECONDS = 0.05


@dataclass(frozen=True)
class ServiceProxyConfig:
    """Policy and interceptor configuration for :class:`ServiceProxy`.

    ``timeout`` applies to each attempt.  ``max_attempts`` includes the first
    call.  The circuit breaker is shared across calls on one proxy instance.
    """

    timeout: Optional[float] = None
    max_attempts: int = 1
    retry_backoff: Callable[[int], float] = field(
        default_factory=lambda: constant_backoff(DEFAULT_RETRY_BACKOFF_SECONDS)
    )
    retry_on: Iterable[Type[BaseException]] = (Exception,)
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    interceptors: tuple[Interceptor, ...] = ()

    def __post_init__(self) -> None:
        if self.timeout is not None and self.timeout <= 0:
            raise ValidationError("ServiceProxyConfig.timeout must be positive")
        if self.max_attempts < 1:
            raise ValidationError("ServiceProxyConfig.max_attempts must be >= 1")
        if self.failure_threshold < 1:
            raise ValidationError("ServiceProxyConfig.failure_threshold must be >= 1")
        if self.recovery_timeout <= 0:
            raise ValidationError(
                "ServiceProxyConfig.recovery_timeout must be positive"
            )
        if self.half_open_max_calls < 1:
            raise ValidationError("ServiceProxyConfig.half_open_max_calls must be >= 1")
        if not isinstance(self.interceptors, tuple):
            object.__setattr__(self, "interceptors", tuple(self.interceptors))


class ServiceProxy:
    """Compose RPC calls from an invoker, interceptors, and resilience policies.

    The proxy resolves a :class:`Method` from the service metadata, runs the
    interceptor chain, then applies retry, circuit-breaking, and timeout
    policies around the injected :class:`ServiceInvoker`.  Transport and
    discovery stay in the invoker; the proxy only owns call semantics.
    """

    def __init__(
        self,
        service: Service,
        invoker: ServiceInvoker,
        config: Optional[ServiceProxyConfig] = None,
    ) -> None:
        self._service = service
        self._invoker = invoker
        self._config = config or ServiceProxyConfig()
        self._breaker = CircuitBreaker(
            failure_threshold=self._config.failure_threshold,
            recovery_timeout=self._config.recovery_timeout,
            half_open_max_calls=self._config.half_open_max_calls,
        )

    @property
    def service(self) -> Service:
        return self._service

    @property
    def invoker(self) -> ServiceInvoker:
        return self._invoker

    @property
    def config(self) -> ServiceProxyConfig:
        return self._config

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._breaker

    async def call(
        self,
        method: MethodSelector,
        payload: Any = None,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Message:
        """Invoke ``method`` with interceptors and resilience policies applied."""
        method_model = self._resolve_method(method)
        request = self._build_request(payload, headers)
        effective_timeout = self._config.timeout if timeout is None else timeout
        if effective_timeout is not None and effective_timeout <= 0:
            raise ValidationError("ServiceProxy timeout must be positive")

        chain = self._build_chain(effective_timeout)

        async def attempt() -> Message:
            context = InvocationContext(
                service=self._service,
                method=method_model,
                request=request,
            )
            try:
                await chain.invoke(context)
            except Exception as exc:
                if context.error is None:
                    context.set_error(exc)
                raise
            if context.error is not None:
                raise context.error
            if context.response is None:
                raise StateError(
                    f"method {method_model.name!r} produced neither response nor error"
                )
            return context.response

        async def protected_attempt() -> Message:
            if effective_timeout is None:
                return await attempt()
            return await TimeoutPolicy(effective_timeout).run(attempt)

        async def protected_call() -> Message:
            return await self._breaker.call(protected_attempt)

        if self._config.max_attempts <= 1:
            return await protected_call()
        retry = RetryPolicy(
            max_attempts=self._config.max_attempts,
            backoff=self._config.retry_backoff,
            retry_on=self._config.retry_on,
        )
        return await retry.run(protected_call)

    def _build_chain(self, timeout: Optional[float]) -> InterceptorChain:
        async def terminal(context: InvocationContext) -> None:
            try:
                response = await self._invoker.invoke(
                    self._service.id,
                    context.method,
                    context.request,
                    headers=dict(context.request.headers),
                    timeout=timeout,
                )
            except Exception as exc:
                context.set_error(exc)
            else:
                context.set_response(response)

        chain = InterceptorChain(terminal)
        for interceptor in self._config.interceptors:
            chain.add_interceptor(interceptor)
        return chain

    def _resolve_method(self, selector: MethodSelector) -> Method:
        if isinstance(selector, Method):
            return selector
        if isinstance(selector, str):
            for method in self._service.methods:
                if method.name == selector:
                    return method
            raise NotFoundError(
                f"method {selector!r} not found in service {self._service.name!r}"
            )
        if isinstance(selector, int) and not isinstance(selector, bool):
            for method in self._service.methods:
                if method.id == selector:
                    return method
            raise NotFoundError(
                f"method id {selector:#x} not found in service {self._service.name!r}"
            )
        raise ValidationError(f"Unsupported method selector: {selector!r}")

    @staticmethod
    def _build_request(payload: Any, headers: Optional[Mapping[str, str]]) -> Message:
        if isinstance(payload, Message):
            if not headers:
                return payload
            return replace(payload, headers={**payload.headers, **headers})
        return Message(payload=payload, headers=dict(headers or {}))
