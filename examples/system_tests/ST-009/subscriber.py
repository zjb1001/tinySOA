import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping
from tinysoa.eventbus.message import EventMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ST-009-SUB")


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
    """Derive consistent (service_id, instance_id) from topic, matching publisher.

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
        return (base_service, base_instance)


async def run_subscriber(sub_id: int, topics: List[str], expected_per_topic: int, results_path: Path) -> None:
    mappings: Dict[str, SomeIPTopicMapping] = {}
    for topic in topics:
        service_id, instance_id = _derive_ids_for_topic(topic)
        mappings[topic] = SomeIPTopicMapping(
            service_id=service_id,
            instance_id=instance_id,
            eventgroup_id=0x0001,
        )

    loop = asyncio.get_running_loop()
    install_quiet_exception_handler(loop)

    # Use unique loopback IP per subscriber like ST-002
    local_ip = f"127.0.{150 + sub_id}.1"
    bus = SomeIPEventBus(mappings=mappings, local_ip=local_ip, publisher_port=34000 + sub_id * 10)

    await bus.start()
    logger.info("Subscriber %s started on %s", sub_id, local_ip)

    # Tracking
    start_time: float = 0.0
    end_time: float = 0.0
    latencies: List[float] = []
    counts: Dict[str, int] = {t: 0 for t in topics}

    done_event = asyncio.Event()

    async def handler(msg: EventMessage):
        nonlocal start_time, end_time
        # Ignore warmup messages
        if msg.payload.get("warmup"):
            logger.debug("Ignoring warmup message")
            return
        now = time.time()
        ts = msg.payload.get("ts", now)
        lat = max(0.0, now - ts)
        if start_time == 0.0:
            start_time = now
        end_time = now
        latencies.append(lat)
        counts[msg.topic] += 1
        # Finish when all topics reach expected count
        if all(counts[t] >= expected_per_topic for t in topics):
            done_event.set()

    for t in topics:
        bus.subscribe(t, handler)
    logger.info("Subscribed to %d topic(s); waiting for internal SD delay...", len(topics))

    try:
        # Allow up to generous timeout
        await asyncio.wait_for(done_event.wait(), timeout=max(30.0, len(topics) * 5.0))
        logger.info("All expected messages received")
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for messages. Received counts: %s", counts)
        await bus.stop()
        sys.exit(1)

    await bus.stop()

    # Prepare results
    results = {
        "sub_id": sub_id,
        "topics": topics,
        "expected_per_topic": expected_per_topic,
        "counts": counts,
        "start_time": start_time,
        "end_time": end_time,
        "duration": max(0.0, end_time - start_time),
        "latencies": latencies,
    }

    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("w") as f:
        json.dump(results, f)
    logger.info("Subscriber %s wrote results to %s", sub_id, results_path)


async def main():
    sub_id = int(os.environ.get("PERF_SUB_ID", "0"))
    topics_raw = os.environ.get("PERF_TOPICS", "perf.topic.shared")
    topics = [t.strip() for t in topics_raw.split(",") if t.strip()]
    expected_per_topic = int(os.environ.get("PERF_EXPECTED_PER_TOPIC", "1000"))
    results_file = Path(os.environ.get("PERF_RESULTS_FILE", f"results/sub_{sub_id}.json"))

    await run_subscriber(sub_id, topics, expected_per_topic, results_file)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
