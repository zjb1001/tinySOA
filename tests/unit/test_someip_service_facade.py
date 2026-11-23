"""Application-facing SomeIPService facade."""

from __future__ import annotations

import pytest

from tinysoa.core.errors import NotFoundError, StateError
from tinysoa.eventbus import (
    SomeIPEndpoint,
    SomeIPService,
    SomeIPServiceBinding,
    SomeIPTopicMapping,
    TopicPublisher,
    TopicSubscriber,
)

TOPIC = "demo.topic"
MAPPING = SomeIPTopicMapping(
    service_id=0x4466, instance_id=0x0001, eventgroup_id=0x0001
)


def _binding(*, methods=None) -> SomeIPServiceBinding:
    return SomeIPServiceBinding(
        name="demo",
        service_id=0x4466,
        instance_id=0x0001,
        methods=methods or {},
    )


async def _handler(_message) -> None:
    return None


def test_service_views_share_one_endpoint() -> None:
    endpoint = SomeIPEndpoint(publisher_port=30740)
    service = SomeIPService(
        _binding(methods={"ping": 0x0001}),
        event_mappings={TOPIC: MAPPING},
        endpoint=endpoint,
    )

    assert service.endpoint is endpoint
    assert service.event_bus is not None
    assert service.event_bus._endpoint is endpoint
    assert service.dispatcher._endpoint is endpoint

    assert isinstance(service.publisher(TOPIC), TopicPublisher)
    assert isinstance(service.subscriber(TOPIC, _handler), TopicSubscriber)


async def test_service_register_requires_start() -> None:
    service = SomeIPService(
        _binding(),
        event_mappings={TOPIC: MAPPING},
        endpoint=SomeIPEndpoint(publisher_port=30745),
    )
    publisher = service.publisher(TOPIC)

    with pytest.raises(StateError, match="not started"):
        await service.register(publisher)


def test_service_subscriber_rejects_unknown_topic() -> None:
    service = SomeIPService(
        _binding(),
        event_mappings={TOPIC: MAPPING},
        endpoint=SomeIPEndpoint(publisher_port=30748),
    )

    with pytest.raises(NotFoundError):
        service.subscriber("other.topic", _handler)


def test_service_publisher_rejects_unknown_topic() -> None:
    service = SomeIPService(
        _binding(),
        event_mappings={TOPIC: MAPPING},
        endpoint=SomeIPEndpoint(publisher_port=30750),
    )
    with pytest.raises(NotFoundError):
        service.publisher("other.topic")


def test_service_method_registration() -> None:
    service = SomeIPService(
        _binding(methods={"ping": 0x0001}),
        endpoint=SomeIPEndpoint(publisher_port=30760),
    )

    async def handler(_payload):
        return {"pong": True}

    service.register_method("ping", handler)
    assert service.dispatcher.has_handlers


async def test_service_invoke_requires_start() -> None:
    service = SomeIPService(
        _binding(methods={"ping": 0x0001}),
        endpoint=SomeIPEndpoint(publisher_port=30770),
    )
    with pytest.raises(StateError):
        await service.invoke("ping", {})
