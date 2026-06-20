from .message import EventMessage
from .bus import (
	EventBus,
	InMemoryEventBus,
	EventHandler,
	Subscription,
	get_event_bus,
	set_event_bus,
)
from .tcp import TCPEventBusClient, TCPEventBusServer

# SomeIPEventBus depends on the vendored pysomeip package (third_party/pysomeip/).
# It is the heavyweight of the three stacks; import it lazily so that a missing
# PYTHONPATH (or a non-installed someip package) doesn't prevent InMemory or
# TCP users from importing *anything* from tinysoa.eventbus.
try:
	from .someip import SomeIPEventBus, SomeIPTopicMapping, SomeIPPublisher, SomeIPSubscriber
except ImportError:  # pragma: no cover — someip is vendored and always present in dev/test
	SomeIPEventBus = None       # type: ignore[assignment]
	SomeIPTopicMapping = None   # type: ignore[assignment]
	SomeIPPublisher = None      # type: ignore[assignment]
	SomeIPSubscriber = None     # type: ignore[assignment]

__all__ = [
	"EventBus",
	"InMemoryEventBus",
	"TCPEventBusClient",
	"TCPEventBusServer",
	"SomeIPEventBus",
	"SomeIPTopicMapping",
	"SomeIPPublisher",
	"SomeIPSubscriber",
	"EventMessage",
	"EventHandler",
	"Subscription",
	"get_event_bus",
	"set_event_bus",
]
