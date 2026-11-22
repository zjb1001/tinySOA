"""SOME/IP one-to-many — shared configuration.

Application code only knows ``TOPIC``.  SOME/IP IDs live here and are consumed
by the ``SomeIPService`` facade.
"""

from tinysoa.eventbus import SomeIPServiceBinding, SomeIPTopicMapping

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

MAPPING = SomeIPTopicMapping(
    service_id=SERVICE_ID,
    instance_id=INSTANCE_ID,
    eventgroup_id=EVENTGROUP_ID,
    major_version=MAJOR_VERSION,
)
EVENT_MAPPINGS = {TOPIC: MAPPING}


def service_binding(
    *,
    local_port: int = 0,
    server_port: int = 0,
    timeout: float = 5.0,
) -> SomeIPServiceBinding:
    """Build the shared service binding (event-only, no methods)."""
    return SomeIPServiceBinding(
        name="demo_one_to_many",
        service_id=SERVICE_ID,
        instance_id=INSTANCE_ID,
        methods={},
        major_version=MAJOR_VERSION,
        local_ip=LOCAL_IP,
        local_port=local_port,
        server_port=server_port,
        timeout=timeout,
    )
