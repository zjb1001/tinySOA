class TinySOAError(Exception):
    """Base exception for tinySOA."""


class ValidationError(TinySOAError):
    """Raised when model validation fails."""


class StateError(TinySOAError):
    """Raised on invalid state transitions or operations."""


class NotFoundError(TinySOAError):
    """Raised when an entity is not found."""


class DuplicateError(TinySOAError):
    """Raised when duplicate identifiers are detected."""
