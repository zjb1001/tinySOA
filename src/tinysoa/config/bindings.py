from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from tinysoa.core.errors import ValidationError


class EventBusKind(str, Enum):
    """Transport family selected by :class:`EventBusConfig`."""

    INMEMORY = "inmemory"
    TCP = "tcp"
    SOMEIP = "someip"


@dataclass(frozen=True)
class TopicBinding:
    """Bind an application topic to transport-specific options.

    The application only uses ``topic``; the options are interpreted by the
    selected :class:`EventBusKind` (e.g. service/instance/eventgroup for SOME/IP).
    """

    topic: str
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.topic:
            raise ValidationError("TopicBinding.topic must be non-empty")
        if not isinstance(self.options, Mapping):
            raise ValidationError("TopicBinding.options must be a mapping")

    def require_int(
        self,
        key: str,
        *,
        default: Optional[int] = None,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> int:
        """Return an integer option, validating presence and range."""
        value = self.options.get(key, default)
        if value is None:
            raise ValidationError(f"TopicBinding[{self.topic}] missing option: {key}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(
                f"TopicBinding[{self.topic}].{key} must be an integer, got {type(value).__name__}"
            )
        if minimum is not None and value < minimum:
            raise ValidationError(
                f"TopicBinding[{self.topic}].{key} must be >= {minimum}, got {value}"
            )
        if maximum is not None and value > maximum:
            raise ValidationError(
                f"TopicBinding[{self.topic}].{key} must be <= {maximum}, got {value}"
            )
        return value

    def require_str(self, key: str, *, default: Optional[str] = None) -> str:
        """Return a string option, validating presence and type."""
        value = self.options.get(key, default)
        if value is None:
            raise ValidationError(f"TopicBinding[{self.topic}] missing option: {key}")
        if not isinstance(value, str) or not value:
            raise ValidationError(
                f"TopicBinding[{self.topic}].{key} must be a non-empty string"
            )
        return value


@dataclass(frozen=True)
class EventBusConfig:
    """Protocol-agnostic event bus configuration.

    ``bindings`` maps application topics to transport identities.  An empty
    binding list is valid for transports that only need endpoint options
    (InMemory/TCP); SOME/IP requires at least one binding.
    """

    kind: EventBusKind = EventBusKind.INMEMORY
    service: Optional[str] = None
    bindings: tuple[TopicBinding, ...] = field(default_factory=tuple)
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EventBusKind):
            try:
                object.__setattr__(self, "kind", EventBusKind(self.kind))
            except ValueError as exc:
                raise ValidationError(f"Unknown EventBusKind: {self.kind!r}") from exc
        if not isinstance(self.bindings, tuple):
            object.__setattr__(self, "bindings", tuple(self.bindings))
        if not isinstance(self.options, Mapping):
            raise ValidationError("EventBusConfig.options must be a mapping")

        topics = [binding.topic for binding in self.bindings]
        if len(topics) != len(set(topics)):
            raise ValidationError("EventBusConfig has duplicate topic bindings")

    def bindings_by_topic(self) -> dict[str, TopicBinding]:
        """Return bindings keyed by topic."""
        return {binding.topic: binding for binding in self.bindings}

    def option_str(self, key: str, default: str) -> str:
        """Return a string endpoint option."""
        value = self.options.get(key, default)
        if not isinstance(value, str) or not value:
            raise ValidationError(f"EventBusConfig.options.{key} must be a string")
        return value

    def option_int(
        self,
        key: str,
        default: int,
        *,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> int:
        """Return an integer endpoint option."""
        value = self.options.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"EventBusConfig.options.{key} must be an integer")
        if minimum is not None and value < minimum:
            raise ValidationError(
                f"EventBusConfig.options.{key} must be >= {minimum}, got {value}"
            )
        if maximum is not None and value > maximum:
            raise ValidationError(
                f"EventBusConfig.options.{key} must be <= {maximum}, got {value}"
            )
        return value

    def option_bool(self, key: str, default: bool) -> bool:
        """Return a boolean endpoint option."""
        value = self.options.get(key, default)
        if not isinstance(value, bool):
            raise ValidationError(f"EventBusConfig.options.{key} must be a boolean")
        return value
