"""
Cross-process SOME/IP pub/sub — shared configuration.

These IDs wire a tinySOA topic to a concrete SOME/IP service. The publisher and
subscriber processes use the SAME mapping so the topic resolves to the same
(service_id, instance_id, eventgroup_id) on both sides.
"""
from __future__ import annotations

import asyncio

from tinysoa.eventbus.someip import SomeIPTopicMapping

# Loopback + SD multicast group used by pysomeip (224.224.224.245:30490).
LOCAL_IP = "127.0.0.1"

# The tinySOA topic. Both processes publish/subscribe this string; the EventBus
# translates it to the SOME/IP identifiers below.
TOPIC = "demo.cross_process"

# SOME/IP service identity for this topic.
SERVICE_ID = 0x2222
INSTANCE_ID = 0x0001
EVENTGROUP_ID = 0x0001
MAJOR_VERSION = 1

# Distinct unicast port bases per role (the EventBus allocates service ports
# above this base). Must differ between publisher and subscriber processes.
PUBLISHER_PORT_BASE = 30700
SUBSCRIBER_PORT_BASE = 30710

MAPPING = SomeIPTopicMapping(
    service_id=SERVICE_ID,
    instance_id=INSTANCE_ID,
    eventgroup_id=EVENTGROUP_ID,
    major_version=MAJOR_VERSION,
)

MAPPINGS = {TOPIC: MAPPING}


def quiet_teardown() -> None:
    """Silence benign teardown races in the underlying SOME/IP stack.

    When ``SomeIPEventBus.stop()`` closes the SD transports, two kinds of
    post-delivery noise can surface (messages have already been sent by then):

    * an in-flight periodic ``_send_subscribe`` touching the loop after
      shutdown begins, raising ``AttributeError: 'NoneType' object has no
      attribute 'call_exception_handler'``;
    * the SD announcer's ``connection_lost`` double-stopping an already-stopped
      task, raising ``RuntimeError: task already stopped``.

    Neither affects correctness. Install this handler to drop just those two
    messages while still logging every real error.
    """
    loop = asyncio.get_running_loop()

    def _handler(loop: asyncio.AbstractEventLoop, context) -> None:  # type: ignore[no-untyped-def]
        exc = context.get("exception")
        if exc is not None:
            message = str(exc)
            if "call_exception_handler" in message or "task already stopped" in message:
                return
        loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)
