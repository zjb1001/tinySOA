"""Minimal runnable echo service demo (engineering-grade).

Showcases the full tinySOA stack in one self-contained example:

  * ``Container`` + ``LifecycleManager`` for service registration/FSM
  * ``InterceptorChain`` (tracing -> metrics -> logging) for cross-cutting concerns
  * Resilience policies: ``RetryPolicy`` wrapping ``CircuitBreaker`` wrapping
    ``TimeoutPolicy`` wrapping the chain
  * ``InMemoryEventBus`` for the request-triggered ``echo.said`` event

Run (from repo root, both packages resolve from source):

    PYTHONPATH=src:tinySOA/src python tinySOA/examples/echo_service/app.py

The demo is deterministic and self-contained (in-memory bus, no network): it
starts the service, subscribes to the ``echo.said`` event, invokes the ``say``
method once, prints the response and the delivered event, then shuts down.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from tinysoa.core.model import Endpoint, Event, Message, Method, Protocol, Service
from tinysoa.eventbus import EventMessage, InMemoryEventBus
from tinysoa.obs.tracing import TracingInterceptor
from tinysoa.policies.circuit_breaker import CircuitBreaker
from tinysoa.policies.retry import RetryPolicy, exponential_backoff
from tinysoa.policies.timeout import TimeoutPolicy
from tinysoa.runtime.container import Container
from tinysoa.runtime.lifecycle import LifecycleManager
from tinysoa.spi.interceptor import (
    InterceptorChain,
    InvocationContext,
    LoggingInterceptor,
    MetricsInterceptor,
)

logger = logging.getLogger("tinysoa.example.echo")

#: Request -> response + event topic used by this demo.
ECHO_TOPIC = "echo.said"


class EchoServiceApp:
    """Compose and run a single echo service behind the framework stack.

    Intentionally a plain class (not a ``@dataclass``): it holds live framework
    objects and mutable runtime state, with a bespoke ``__init__`` wiring the
    container, policies and interceptor chain.
    """

    def __init__(self) -> None:
        self.container = Container()
        self.lifecycle = LifecycleManager(self.container)
        self.event_bus = InMemoryEventBus()

        self.service = Service(
            name="echo",
            id=1,
            version="1.0.0",
            methods=[Method("say", 1)],
            events=[Event("said", 1)],
            endpoints=[Endpoint("localhost", 9000, Protocol.TCP)],
        )
        self.container.add_service(self.service)

        # Cross-cutting interceptors (lower priority runs earlier).
        self.tracing = TracingInterceptor()
        self.metrics = MetricsInterceptor()
        self.logging = LoggingInterceptor()

        # Resilience policies: retry wraps circuit-breaker wraps timeout.
        self.retry = RetryPolicy(
            max_attempts=3, backoff=exponential_backoff(0.05, factor=2, max_delay=0.2)
        )
        self.timeout = TimeoutPolicy(timeout_seconds=1.0)
        self.circuit = CircuitBreaker(
            failure_threshold=3, recovery_timeout=2.0, half_open_max_calls=1
        )

        # Interceptor chain terminating at the actual business invoker.
        self.chain = InterceptorChain(self._actual_invoker)
        self.chain.add_interceptor(self.tracing)
        self.chain.add_interceptor(self.metrics)
        self.chain.add_interceptor(self.logging)

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self.lifecycle.start_service(self.service.id)

    def stop(self) -> None:
        self.lifecycle.stop_service(self.service.id)

    def terminate(self) -> None:
        self.lifecycle.terminate_service(self.service.id)

    # ------------------------------------------------------------------ invocation

    async def _actual_invoker(self, ctx: InvocationContext) -> None:
        """Echo business logic: reflect the payload and emit an event."""
        payload = ctx.request.payload
        result = {
            "echo": payload,
            "service": ctx.service.name,
            "method": ctx.method.name,
        }
        ctx.set_response(Message(payload=result))

        await self.event_bus.publish(
            EventMessage(
                topic=ECHO_TOPIC,
                payload=result,
                trace_id=ctx.metadata.get("trace_id"),
            )
        )

    async def _invoke_chain(self, ctx: InvocationContext) -> None:
        await self.chain.invoke(ctx)

    async def invoke(self, payload: Any) -> Message:
        """Invoke ``say`` through retry -> circuit-breaker -> timeout -> chain."""
        ctx = InvocationContext(
            service=self.service,
            method=self.service.methods[0],
            request=Message(payload=payload),
        )

        async def _do_invoke() -> Any:
            # Circuit breaker wraps timeout; timeout wraps the interceptor chain.
            return await self.circuit.call(
                lambda: self.timeout.run(lambda: self._invoke_chain(ctx))
            )

        await self.retry.run(_do_invoke)

        if ctx.error is not None:
            raise ctx.error
        return ctx.response

    # ------------------------------------------------------------------ event helpers

    def subscribe_said(self, handler: Callable[[EventMessage], Awaitable[None]]):
        """Subscribe ``handler`` to the ``echo.said`` event; return the token."""
        return self.event_bus.subscribe(ECHO_TOPIC, handler)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    app = EchoServiceApp()
    app.start()
    logger.info("echo service started (service_id=%s)", app.service.id)

    async def on_said(msg: EventMessage) -> None:
        logger.info("event received: %s", msg.payload)

    app.subscribe_said(on_said)

    try:
        logger.info("invoking echo service...")
        response = await app.invoke("Hello Async World")
        logger.info("response: %s", response.payload)
    except Exception as exc:  # noqa: BLE001 - demo surfaces any invocation failure
        logger.error("invocation failed: %s", exc, exc_info=True)
    finally:
        app.stop()
        app.terminate()
        logger.info("echo service terminated")


if __name__ == "__main__":
    asyncio.run(main())
