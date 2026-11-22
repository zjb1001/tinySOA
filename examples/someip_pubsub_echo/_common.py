"""SOME/IP Echo — shared configuration.

The application code only uses ``TOPIC``.  SOME/IP identities and endpoints
live here, in the configuration layer, and are translated by
``tinysoa.config.create_event_bus``.
"""

from tinysoa.config import EventBusConfig, EventBusKind, TopicBinding

TOPIC = "echo.hello"

SERVICE_ID = 0x3333
INSTANCE_ID = 0x0001
EVENTGROUP_ID = 0x0001
MAJOR_VERSION = 1

LOCAL_IP = "127.0.0.1"

# 两个进程用不同端口，避免冲突
PUBLISHER_PORT = 30900
SUBSCRIBER_PORT = 30910


def _config(*, is_publisher: bool) -> EventBusConfig:
    return EventBusConfig(
        kind=EventBusKind.SOMEIP,
        service="echo",
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
            "publisher_port": PUBLISHER_PORT if is_publisher else SUBSCRIBER_PORT,
            "is_publisher": is_publisher,
        },
    )


def publisher_config() -> EventBusConfig:
    """Bus config for the publisher process."""
    return _config(is_publisher=True)


def subscriber_config() -> EventBusConfig:
    """Bus config for the subscriber process."""
    return _config(is_publisher=False)
