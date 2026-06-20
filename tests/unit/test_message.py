"""Unit tests for EventMessage — serialization, validation, edge cases."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from tinysoa.eventbus.message import EventMessage


class TestEventMessageConstruction:
    def test_minimal_message_has_auto_generated_fields(self) -> None:
        msg = EventMessage(topic="test.topic", payload={"k": "v"})
        assert msg.topic == "test.topic"
        assert msg.payload == {"k": "v"}
        assert isinstance(msg.message_id, uuid.UUID)
        assert isinstance(msg.timestamp, datetime)

    def test_message_id_is_valid_uuid(self) -> None:
        msg = EventMessage(topic="foo.bar", payload=None)
        assert isinstance(msg.message_id, uuid.UUID)


class TestEventMessageSerialization:
    def test_roundtrip_preserves_all_fields(self) -> None:
        original = EventMessage(topic="a.b", payload={"x": 1})
        restored = EventMessage.from_dict(original.to_dict())
        assert restored.topic == "a.b"
        assert restored.payload == {"x": 1}
        assert str(restored.message_id) == str(original.message_id)

    def test_to_json_produces_valid_json(self) -> None:
        msg = EventMessage(topic="test.topic", payload={"key": "value"})
        s = msg.to_json()
        data = json.loads(s)
        assert data["topic"] == "test.topic"

    def test_from_json_reconstructs_message(self) -> None:
        original = EventMessage(topic="x.y", payload=[1, 2, 3])
        restored = EventMessage.from_json(original.to_json())
        assert restored.topic == "x.y"
        assert restored.payload == [1, 2, 3]

    def test_from_json_with_invalid_raises(self) -> None:
        with pytest.raises((json.JSONDecodeError, KeyError, ValueError)):
            EventMessage.from_json("not valid json {{{{")

    def test_from_dict_missing_topic_raises(self) -> None:
        with pytest.raises(KeyError):
            EventMessage.from_dict({"payload": None})

    def test_from_dict_with_extra_fields_ignores_them(self) -> None:
        msg = EventMessage.from_dict({
            "topic": "test.topic",
            "payload": None,
            "unknown_field": "should be ignored",
        })
        assert msg.topic == "test.topic"
