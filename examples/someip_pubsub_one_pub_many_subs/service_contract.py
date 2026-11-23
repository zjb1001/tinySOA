"""Shared event contract for the SOME/IP one-to-many example.

Both processes import this module, so the topic and SOME/IP IDs used by the
publisher and subscribers cannot drift apart.  Application code only needs
``TOPIC``; the IDs stay in this contract.
"""

from tinysoa.eventbus import SomeIPServiceBinding, SomeIPTopicMapping

SERVICE_NAME = "demo_one_to_many"
TOPIC = "demo.one_to_many"

SERVICE_ID = 0x3344
INSTANCE_ID = 0x0001
EVENTGROUP_ID = 0x0001
MAJOR_VERSION = 1

LOCAL_IP = "127.0.0.1"

# Publisher unicast service endpoint base.
PUBLISHER_PORT = 30920

# Subscriber binding port bases (distinct per process to avoid collisions).
SUBSCRIBER_PORT_BASE = 30930
SUBSCRIBER_PORT_STEP = 10

EVENT_MAPPING = SomeIPTopicMapping(
    service_id=SERVICE_ID,
    instance_id=INSTANCE_ID,
    eventgroup_id=EVENTGROUP_ID,
    major_version=MAJOR_VERSION,
)
EVENT_MAPPINGS = {TOPIC: EVENT_MAPPING}


def _config(
    *,
    local_port: int = 0,
    server_port: int = 0,
    timeout: float = 5.0,
) -> SomeIPServiceBinding:
    """Build a pure configuration object; no I/O or socket binding happens."""
    return SomeIPServiceBinding(
        name=SERVICE_NAME,
        service_id=SERVICE_ID,
        instance_id=INSTANCE_ID,
        methods={},
        major_version=MAJOR_VERSION,
        local_ip=LOCAL_IP,
        local_port=local_port,
        server_port=server_port,
        timeout=timeout,
    )


def publisher_config(server_port: int) -> SomeIPServiceBinding:
    """Publisher endpoint for this event contract."""
    return _config(server_port=server_port)


def subscriber_config(local_port: int) -> SomeIPServiceBinding:
    """Subscriber endpoint for this event contract."""
    return _config(local_port=local_port)
