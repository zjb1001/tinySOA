"""SOME/IP one-to-many — shared configuration.

Application code only knows ``TOPIC``.  The SOME/IP service/eventgroup IDs and
local endpoint options live here and are consumed by ``create_event_bus``.
"""

from tinysoa.config import EventBusConfig, EventBusKind, TopicBinding

TOPIC = "demo.one_to_many"

SERVICE_ID = 0x3344
INSTANCE_ID = 0x0001
EVENTGROUP_ID = 0x0001
MAJOR_VERSION = 1

LOCAL_IP = "127.0.0.1"

# Publisher unicast service endpoint base.
PUBLISHER_PORT = 30920

# Subscriber local port bases (distinct per process to avoid collisions).
SUBSCRIBER_PORT_BASE = 30930
SUBSCRIBER_PORT_STEP = 10


def _config(*, is_publisher: bool, local_port: int) -> EventBusConfig:
    return EventBusConfig(
        kind=EventBusKind.SOMEIP,
        service="demo_one_to_many",
        bindings=(
            TopicBinding(
                TOPIC,
                {
                    "service_id": SERVICE_ID,
                    "instance_id": INSTANCE_ID,
                    "eventgroup_id": EVENTGROUP_ID,
                    "major_version": MAJOR_VERSION,
                },
            ),
        ),
        options={
            "local_ip": LOCAL_IP,
            "publisher_port": local_port,
            "is_publisher": is_publisher,
        },
    )


def publisher_config() -> EventBusConfig:
    """Bus config for the publisher process."""
    return _config(is_publisher=True, local_port=PUBLISHER_PORT)


def subscriber_config(
    local_port: int = SUBSCRIBER_PORT_BASE,
) -> EventBusConfig:
    """Bus config for one subscriber process."""
    return _config(is_publisher=False, local_port=local_port)
