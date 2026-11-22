"""Contract tests for SOME/IP method bindings and invoker selectors."""

from __future__ import annotations

import pytest

from tinysoa.core.errors import NotFoundError, StateError, ValidationError
from tinysoa.core.model import Method, Service
from tinysoa.eventbus import (
    SomeIPMethodDispatcher,
    SomeIPMethodInvoker,
    SomeIPServiceBinding,
)

METHODS = {"add": 0x0001, "subtract": 0x0002, "multiply": 0x0003}


def _binding(**overrides) -> SomeIPServiceBinding:
    values = {
        "name": "calc",
        "service_id": 0x4444,
        "instance_id": 0x0001,
        "methods": METHODS,
    }
    values.update(overrides)
    return SomeIPServiceBinding(**values)


def test_binding_resolves_methods_by_name_id_and_method() -> None:
    binding = _binding()
    assert binding.method_id("add") == 0x0001
    assert binding.method_id(0x0002) == 0x0002
    assert binding.method_id(Method("multiply", 0x0003)) == 0x0003


def test_binding_rejects_unknown_method() -> None:
    binding = _binding()
    with pytest.raises(NotFoundError):
        binding.method_id("divide")
    with pytest.raises(NotFoundError):
        binding.method_id(0x00FF)


def test_binding_matches_service_selectors() -> None:
    binding = _binding()
    assert binding.matches_service("calc")
    assert binding.matches_service(0x4444)
    assert binding.matches_service(Service(name="calc", id=0x4444, version="1"))
    assert not binding.matches_service("other")
    assert not binding.matches_service(0x1111)


def test_binding_copies_method_map() -> None:
    methods = {"add": 1}
    binding = _binding(methods=methods)
    methods["subtract"] = 2
    assert binding.methods == {"add": 1}


def test_binding_rejects_duplicate_method_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate method ids"):
        _binding(methods={"a": 1, "b": 1})


def test_binding_rejects_invalid_ids_and_timeouts() -> None:
    with pytest.raises(ValidationError):
        _binding(service_id=0x10000)
    with pytest.raises(ValidationError):
        _binding(timeout=0)


async def test_invoker_rejects_use_before_start() -> None:
    invoker = SomeIPMethodInvoker(_binding())
    with pytest.raises(StateError):
        await invoker.invoke("calc", "add", {"a": 1, "b": 2})


async def test_invoker_rejects_service_and_method_mismatch() -> None:
    invoker = SomeIPMethodInvoker(_binding())
    # Mark started to get past the lifecycle guard without opening sockets.
    invoker._started = True

    with pytest.raises(NotFoundError):
        await invoker.invoke("other", "add", {})
    with pytest.raises(NotFoundError):
        await invoker.invoke("calc", "divide", {})


def test_dispatcher_rejects_unknown_and_duplicate_methods() -> None:
    dispatcher = SomeIPMethodDispatcher(_binding())

    async def handler(_payload):
        return None

    with pytest.raises(NotFoundError):
        dispatcher.register("divide", handler)
    dispatcher.register("add", handler)
    with pytest.raises(ValidationError):
        dispatcher.register("add", handler)
