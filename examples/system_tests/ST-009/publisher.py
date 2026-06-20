import asyncio
import logging
import os
import sys
import time
from typing import Dict, List

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-009-PUB")


def install_quiet_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    default_handler = loop.get_exception_handler() or loop.default_exception_handler

    def handler(loop_ref, ctx):
        exc = ctx.get("exception")
        if isinstance(exc, RuntimeError) and "task already stopped" in str(exc):
            logger.debug("Swallowing expected RuntimeError during shutdown: %s", exc)
            return
        if isinstance(exc, AttributeError) and ("sendto" in str(exc) or "call_exception_handler" in str(exc)):
            logger.debug("Swallowing expected AttributeError during shutdown: %s", exc)
            return
        default_handler(ctx)

    loop.set_exception_handler(handler)


def _derive_ids_for_topic(topic: str) -> tuple[int, int]:
    """Derive consistent (service_id, instance_id) from topic.

    Rules:
    - perf.topic.shared -> (0x1200, 0x0100)
    - perf.topic.<N>    -> (0x1200 + N, 0x0100)
    """
    base_service = 0x1200
    base_instance = 0x0100
    if topic.endswith(".shared"):
        return (base_service, base_instance)
    try:
        n = int(topic.rsplit(".", 1)[-1])
        return (base_service + n, base_instance)
    except ValueError:
        # Fallback to shared mapping
        return (base_service, base_instance)


async def run_publisher(pub_id: int, topics: List[str], messages_per_topic: int, interval_s: float) -> None:
    mappings: Dict[str, SomeIPTopicMapping] = {}
    # Use per-topic deterministic mapping so subscribers can match
    for topic in topics:
        service_id, instance_id = _derive_ids_for_topic(topic)
        mappings[topic] = SomeIPTopicMapping(
            service_id=service_id,
            instance_id=instance_id,
            eventgroup_id=0x0001,
        )

    loop = asyncio.get_running_loop()
    install_quiet_exception_handler(loop)

    # Use unique loopback IP per publisher like ST-002
    local_ip = f"127.0.{100 + pub_id}.1"
    bus = SomeIPEventBus(mappings=mappings, local_ip=local_ip, publisher_port=33000 + pub_id * 10)

    await bus.start()
    logger.info("Publisher %s started on %s", pub_id, local_ip)

    # Trigger service announcement by publishing a dummy message
    for topic in topics:
        dummy = {"warmup": True, "ts": time.time()}
        await bus.publish(EventMessage(topic=topic, payload=dummy))
    logger.info("Publisher %s announced services", pub_id)

    # Allow subscribers to finish their internal SD subscription delay and connect
    await asyncio.sleep(8.0)

    # Send messages
    start = time.time()
    total = 0
    for topic in topics:
        for i in range(messages_per_topic):
            payload = {
                "seq": i,
                "pub_id": pub_id,
                "topic": topic,
                "ts": time.time(),
            }
            await bus.publish(EventMessage(topic=topic, payload=payload))
            total += 1
            if interval_s > 0:
                await asyncio.sleep(interval_s)
    end = time.time()
    logger.info("Publisher %s sent %s messages in %.3fs (%.1f msg/s)", pub_id, total, end - start, total / max(end - start, 1e-6))

    # Wait longer to allow subscribers to receive all messages before shutting down
    await asyncio.sleep(3.0)
    await bus.stop()
    logger.info("Publisher %s stopped", pub_id)


async def main():
    pub_id = int(os.environ.get("PERF_PUB_ID", "0"))
    # Topics as comma-separated list
    topics_raw = os.environ.get("PERF_TOPICS", "perf.topic.shared")
    topics = [t.strip() for t in topics_raw.split(",") if t.strip()]
    messages_per_topic = int(os.environ.get("PERF_MESSAGES_PER_TOPIC", "1000"))
    interval_s = float(os.environ.get("PERF_INTERVAL_S", "0"))

    await run_publisher(pub_id, topics, messages_per_topic, interval_s)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
