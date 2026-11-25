"""Typed control-plane events and the concrete in-process dispatcher."""

from __future__ import annotations

import asyncio

import pytest

from tinysoa.core.errors import ValidationError
from tinysoa.runtime import (
    InternalEvent,
    InternalEventDispatcher,
    InternalEventType,
)


def test_event_factories_set_source_and_related() -> None:
    ready = InternalEvent.service_ready(0x10, name="engine")
    assert ready.event_type is InternalEventType.SERVICE_READY
    assert ready.source_service_id == 0x10
    assert ready.related_service_id == 0x10
    assert ready.details["name"] == "engine"
    assert ready.details["status"] == "running"

    satisfied = InternalEvent.dependency_satisfied(0x20, 0x10)
    assert satisfied.event_type is InternalEventType.DEPENDENCY_SATISFIED
    assert satisfied.source_service_id == 0x20
    assert satisfied.related_service_id == 0x10

    discovered = InternalEvent.instance_discovered(0x10, 1)
    assert discovered.related_service_id == 0x10
    assert discovered.related_instance_id == 1


def test_event_details_are_read_only() -> None:
    event = InternalEvent.service_ready(1)

    with pytest.raises(TypeError):
        event.details["status"] = "changed"  # type: ignore[index]


def test_event_validates_contract() -> None:
    with pytest.raises(ValidationError):
        InternalEvent(event_type="service.ready", source_service_id=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        InternalEvent(InternalEventType.SERVICE_READY, -1)
    with pytest.raises(ValidationError):
        InternalEvent(InternalEventType.SERVICE_READY, 1, related_service_id=-1)
    with pytest.raises(ValidationError):
        InternalEvent(InternalEventType.SERVICE_READY, 1, related_instance_id=-1)
    with pytest.raises(ValidationError):
        InternalEvent(InternalEventType.SERVICE_READY, 1, details="bad")  # type: ignore[arg-type]


def test_event_to_dict() -> None:
    event = InternalEvent.dependency_lost(0x20, 0x10, required=True)

    data = event.to_dict()

    assert data["event_type"] == "dependency.lost"
    assert data["source_service_id"] == 0x20
    assert data["related_service_id"] == 0x10
    assert data["details"]["required"] is True
    assert isinstance(data["correlation_id"], str)


async def test_dispatcher_fanout_in_subscription_order() -> None:
    dispatcher = InternalEventDispatcher()
    received: list[str] = []

    async def first(event: InternalEvent) -> None:
        received.append("first")

    async def second(event: InternalEvent) -> None:
        received.append("second")

    dispatcher.subscribe(InternalEventType.SERVICE_READY, first)
    dispatcher.subscribe(InternalEventType.SERVICE_READY, second)
    event = InternalEvent.service_ready(1)

    await dispatcher.publish(event)

    assert received == ["first", "second"]
    assert dispatcher.history() == [event]
    assert dispatcher.subscriber_count(InternalEventType.SERVICE_READY) == 2
    assert dispatcher.subscriber_count() == 2


async def test_dispatcher_isolates_handler_errors() -> None:
    dispatcher = InternalEventDispatcher()
    received: list[InternalEvent] = []

    async def failing(event: InternalEvent) -> None:
        raise RuntimeError("boom")

    async def ok(event: InternalEvent) -> None:
        received.append(event)

    dispatcher.subscribe(InternalEventType.SERVICE_READY, failing)
    dispatcher.subscribe(InternalEventType.SERVICE_READY, ok)
    event = InternalEvent.service_ready(1)

    await dispatcher.publish(event)

    assert received == [event]


async def test_dispatcher_unsubscribe_and_history_filter() -> None:
    dispatcher = InternalEventDispatcher()
    received: list[InternalEvent] = []

    async def handler(event: InternalEvent) -> None:
        received.append(event)

    subscription = dispatcher.subscribe(InternalEventType.SERVICE_READY, handler)
    ready = InternalEvent.service_ready(1)
    stopped = InternalEvent.service_stopped(1)

    await dispatcher.publish(ready)
    await dispatcher.publish(stopped)
    dispatcher.unsubscribe(subscription)
    dispatcher.unsubscribe(subscription)
    await dispatcher.publish(InternalEvent.service_ready(2))

    assert received == [ready]
    assert len(dispatcher.history(InternalEventType.SERVICE_READY)) == 2
    assert dispatcher.history(limit=1)[0].source_service_id == 2
    assert dispatcher.history(limit=0) == []
    assert dispatcher.subscriber_count() == 0


async def test_dispatcher_async_iter() -> None:
    dispatcher = InternalEventDispatcher()
    received: list[InternalEvent] = []

    async def consume() -> None:
        iterator = dispatcher.subscribe_async_iter(InternalEventType.SERVICE_READY)
        try:
            async for event in iterator:
                received.append(event)
                break
        finally:
            await iterator.aclose()

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    event = InternalEvent.service_ready(1)

    await dispatcher.publish(event)
    await asyncio.wait_for(task, timeout=1.0)

    assert received == [event]
    assert dispatcher.subscriber_count(InternalEventType.SERVICE_READY) == 0


async def test_dispatcher_validates_arguments() -> None:
    dispatcher = InternalEventDispatcher()

    async def handler(event: InternalEvent) -> None:
        return None

    with pytest.raises(ValidationError):
        dispatcher.subscribe("service.ready", handler)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        dispatcher.subscribe(InternalEventType.SERVICE_READY, object())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        await dispatcher.publish(object())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        InternalEventDispatcher(history_size=0)
