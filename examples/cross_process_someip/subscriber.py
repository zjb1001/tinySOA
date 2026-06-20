"""
Cross-process SOME/IP subscriber.

Runs as its OWN OS process. Discovers the publisher's SOME/IP service (via
tinySOA's SomeIPEventBus on top of pysomeip) and receives `demo.cross_process`
events that a publisher in a DIFFERENT process published.

Run (from repo root, no install needed — both packages resolve from source):

    PYTHONPATH=src:tinySOA/src python tinySOA/examples/cross_process_someip/subscriber.py [want] [timeout]

Exit code 0 if it received at least `want` (default 5) events, 1 otherwise.
This exit code is what the orchestrator / pytest test asserts on.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from tinysoa.eventbus.message import EventMessage
from tinysoa.eventbus.someip import SomeIPEventBus

from examples.cross_process_someip import (
    LOCAL_IP,
    MAPPINGS,
    SUBSCRIBER_PORT_BASE,
    TOPIC,
    quiet_teardown,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SUBSCRIBER")


async def main() -> int:
    quiet_teardown()
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

    # is_publisher=False: discovery-only — find + subscribe, do not announce.
    bus = SomeIPEventBus(
        MAPPINGS,
        local_ip=LOCAL_IP,
        publisher_port=SUBSCRIBER_PORT_BASE,
        is_publisher=False,
    )

    received: list[dict] = []
    done = asyncio.Event()

    async def on_event(msg: EventMessage) -> None:
        payload = msg.payload if isinstance(msg.payload, dict) else {"raw": msg.payload}
        received.append(payload)
        logger.info("RECEIVED seq=%s -> %s", payload.get("seq"), payload)
        if len(received) >= want:
            done.set()

    logger.info("starting, waiting for up to %d events (timeout %.0fs)", want, timeout)
    await bus.start()
    sub = bus.subscribe(TOPIC, on_event)

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
        logger.info("SUCCESS received %d/%d events", len(received), want)
        result = 0 if len(received) >= want else 1
    except asyncio.TimeoutError:
        logger.error("TIMEOUT received only %d/%d events", len(received), want)
        result = 1
    finally:
        bus.unsubscribe(sub)
        await bus.stop()
        logger.info("stopped after receiving %d events", len(received))

    return result


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
