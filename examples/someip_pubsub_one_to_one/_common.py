"""SOME/IP one-to-one — shared configuration.

Application code only knows ``TOPIC``.  The SOME/IP service/eventgroup IDs and
local endpoint options live here and are consumed by ``SomeIPService``.
"""

from tinysoa.eventbus import SomeIPServiceBinding, SomeIPTopicMapping

TOPIC = "demo.one_to_one"

SERVICE_ID = 0x3355
INSTANCE_ID = 0x0001
EVENTGROUP_ID = 0x0001
MAJOR_VERSION = 1

LOCAL_IP = "127.0.0.1"

# Publisher unicast service endpoint base.
PUBLISHER_PORT = 30970

# Subscriber local port base; the actual receive port is negotiated via SD.
SUBSCRIBER_PORT = 30980

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
        name="demo_one_to_one",
        service_id=SERVICE_ID,
        instance_id=INSTANCE_ID,
        methods={},
        major_version=MAJOR_VERSION,
        local_ip=LOCAL_IP,
        local_port=local_port,
        server_port=server_port,
        timeout=timeout,
    )
