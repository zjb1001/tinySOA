from .broker import BrokerEventBus
from .bus import (
    EventBus,
    EventBusBroker,
    EventHandler,
    ManagedEventBus,
    Subscription,
    TopicPublisher,
    TopicSubscriber,
    Topology,
    get_event_bus,
    set_event_bus,
)
from .memory import InMemoryEventBus
from .message import EventMessage
from .stream import MessageStream
from .tcp import (
    TCPEventBus,
    TCPEventBusBroker,
    TCPEventBusClient,
    TCPEventBusServer,
    TCPMessageStream,
)

# SomeIPEventBus depends on the vendored pysomeip package (third_party/pysomeip/).
# It is the heavyweight of the three stacks; import it lazily so that a missing
# PYTHONPATH (or a non-installed someip package) doesn't prevent InMemory or
# TCP users from importing *anything* from tinysoa.eventbus.
try:
    from .someip import (
        SomeIPEndpoint,
        SomeIPEventBus,
        SomeIPPublisher,
        SomeIPServiceInstance,
        SomeIPSubscriber,
        SomeIPTopicMapping,
    )
    from .someip_method import (
        SomeIPMethodDispatcher,
        SomeIPMethodInvoker,
        SomeIPRemoteError,
        SomeIPServiceBinding,
    )
    from .someip_service import SomeIPService
except ImportError:  # pragma: no cover — someip is vendored and always present
    SomeIPEndpoint = None  # type: ignore[assignment,misc]
    SomeIPEventBus = None  # type: ignore[assignment,misc]
    SomeIPTopicMapping = None  # type: ignore[assignment,misc]
    SomeIPPublisher = None  # type: ignore[assignment,misc]
    SomeIPServiceInstance = None  # type: ignore[assignment,misc]
    SomeIPSubscriber = None  # type: ignore[assignment,misc]
    SomeIPMethodDispatcher = None  # type: ignore[assignment,misc]
    SomeIPMethodInvoker = None  # type: ignore[assignment,misc]
    SomeIPRemoteError = None  # type: ignore[assignment,misc]
    SomeIPServiceBinding = None  # type: ignore[assignment,misc]
    SomeIPService = None  # type: ignore[assignment,misc]

__all__ = [
    "EventBus",
    "EventBusBroker",
    "BrokerEventBus",
    "ManagedEventBus",
    "MessageStream",
    "Topology",
    "InMemoryEventBus",
    "TCPEventBus",
    "TCPEventBusBroker",
    "TCPEventBusClient",
    "TCPEventBusServer",
    "TCPMessageStream",
    "SomeIPEndpoint",
    "SomeIPEventBus",
    "SomeIPTopicMapping",
    "SomeIPPublisher",
    "SomeIPServiceInstance",
    "SomeIPSubscriber",
    "SomeIPMethodDispatcher",
    "SomeIPMethodInvoker",
    "SomeIPRemoteError",
    "SomeIPService",
    "SomeIPServiceBinding",
    "EventMessage",
    "EventHandler",
    "Subscription",
    "TopicPublisher",
    "TopicSubscriber",
    "get_event_bus",
    "set_event_bus",
]
