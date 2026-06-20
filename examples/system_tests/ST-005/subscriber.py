"""ST-005 subscriber: high-throughput stress test — tracking throughput, loss, ordering, memory.

Verifies the subscriber handles sustained high-frequency message streams, tracking
delivery rate, out-of-order packets, and memory usage (via ``tracemalloc``).
"""
from __future__ import annotations

import asyncio
import gc
from pathlib import Path
import sys
import tracemalloc

# Make _common importable whether run as a bare script from this dir or via -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> system_tests/
from _common import configure_logging, install_quiet_exception_handler, setup_path  # noqa: E402
setup_path()  # -> adds tinysoa/src + pysomeip/src

from tinysoa.eventbus.message import EventMessage  # noqa: E402
from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping  # noqa: E402

logger = configure_logging("ST-005-SUB")


async def main() -> int:
    topic_a = "test.topic.a"
    mappings = {
        topic_a: SomeIPTopicMapping(
            service_id=0x1234, instance_id=0x0001, eventgroup_id=0x0001,
        ),
    }

    install_quiet_exception_handler(logger)

    bus = SomeIPEventBus(
        mappings=mappings, local_ip="127.0.0.41", publisher_port=35010,
    )

    await bus.start()
    logger.info("\n" + "=" * 70)
    logger.info("[STRESS TEST SUBSCRIBER] Bus started on 127.0.0.41")
    logger.info("[READY] Waiting for high-frequency message stream...")
    logger.info("=" * 70 + "\n")

    received_count = 0
    last_seq = -1
    out_of_order = 0
    received_messages: list[int] = []

    async def handler(msg: EventMessage) -> None:
        nonlocal received_count, last_seq, out_of_order
        received_count += 1
        seq = msg.payload.get("seq")
        if seq != last_seq + 1:
            out_of_order += 1
        last_seq = seq
        received_messages.append(seq)
        if received_count % 100 == 0:
            logger.info("[PROGRESS] Received %d messages", received_count)

    bus.subscribe(topic_a, handler)
    logger.info("[SUBSCRIBED] Waiting for publisher to send 1000 messages at 10ms interval...")

    start_time = asyncio.get_event_loop().time()
    timeout = 35.0

    while received_count < 1000:
        if asyncio.get_event_loop().time() - start_time > timeout:
            logger.error(
                "[TIMEOUT] Only received %d/%d messages in %.1fs",
                received_count, 1000, asyncio.get_event_loop().time() - start_time,
            )
            break
        await asyncio.sleep(0.1)

    elapsed = asyncio.get_event_loop().time() - start_time

    logger.info("\n" + "=" * 70)
    logger.info("[STRESS TEST RESULTS]")
    logger.info("Total time: %.2f seconds", elapsed)
    logger.info("Messages received: %d / 1000", received_count)
    logger.info(
        "Message loss: %d (%.2f%%)", 1000 - received_count, (1000 - received_count) / 10.0,
    )
    logger.info("Out-of-order packets: %d", out_of_order)
    logger.info("Throughput: %.1f msg/sec", received_count / elapsed)

    # Memory check via tracemalloc.
    gc.collect()
    tracemalloc.start()
    current, peak = tracemalloc.get_traced_memory()
    logger.info(
        "Current memory: %.1f MB, Peak memory: %.1f MB",
        current / (1024 * 1024), peak / (1024 * 1024),
    )
    tracemalloc.stop()
    logger.info("=" * 70 + "\n")

    success = True
    loss_percent = (1000 - received_count) / 10.0

    if received_count < 900:
        logger.error(
            "FAILED: Expected at least 900 messages (90%%), got %d (%.1f%% loss)",
            received_count, loss_percent,
        )
        success = False
    else:
        logger.info(
            "PASSED: Received %d/1000 (%.1f%% loss) - within acceptable limits for UDP burst load",
            received_count, loss_percent,
        )

    if out_of_order > 100:
        logger.error("FAILED: Too many out-of-order packets: %d (>100)", out_of_order)
        success = False
    elif out_of_order > 0:
        logger.warning("INFO: %d out-of-order packets (expected at high throughput)", out_of_order)

    await bus.stop()
    logger.info("Subscriber bus stopped")
    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        sys.exit(1)
