"""Run 1v1, 1vN and Nv1 pub/sub scenarios on the in-memory event bus.

This example isolates the application-facing API: it only knows topics and
handlers.  The event bus is built by ``create_event_bus(EventBusConfig(...))``,
so the same scenario code can later run over TCP or SOME/IP.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

from tinysoa.config import EventBusConfig, EventBusKind, create_event_bus
from tinysoa.eventbus import EventMessage, ManagedEventBus

TOPIC = "demo.topic"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True)
class ScenarioResult:
    """Deterministic outcome of one topology scenario."""

    name: str
    published: int
    delivered: Dict[str, int]
    sources: Tuple[str, ...] = ()


async def _new_bus() -> ManagedEventBus:
    bus = create_event_bus(EventBusConfig(kind=EventBusKind.INMEMORY))
    await bus.start()
    return bus


async def run_one_to_one(count: int = 3) -> ScenarioResult:
    """One publisher → one subscriber."""
    bus = await _new_bus()
    received = 0

    async def on_event(_message: EventMessage) -> None:
        nonlocal received
        received += 1

    publisher = bus.publisher(TOPIC)
    subscriber = bus.subscriber(TOPIC)
    subscriber.on(on_event)
    try:
        await publisher.register()
        for i in range(count):
            await publisher.publish({"from": "pub-1", "seq": i})
    finally:
        await bus.stop()
    return ScenarioResult("1v1", count, {"sub-1": received})


async def run_one_to_many(subscribers: int = 3, count: int = 5) -> ScenarioResult:
    """One publisher → N subscribers."""
    bus = await _new_bus()
    delivered = {f"sub-{i}": 0 for i in range(1, subscribers + 1)}

    for subscriber_id in delivered:

        async def on_event(_message: EventMessage, name: str = subscriber_id) -> None:
            delivered[name] += 1

        bus.subscriber(TOPIC).on(on_event)

    publisher = bus.publisher(TOPIC)
    try:
        await publisher.register()
        for i in range(count):
            await publisher.publish({"from": "pub-1", "seq": i})
    finally:
        await bus.stop()
    return ScenarioResult("1vN", count, delivered)


async def run_many_to_one(publishers: int = 3, count: int = 5) -> ScenarioResult:
    """N publishers → one subscriber."""
    bus = await _new_bus()
    received: list[dict] = []

    async def on_event(message: EventMessage) -> None:
        received.append(message.payload)

    bus.subscriber(TOPIC).on(on_event)
    publishers_list = [bus.publisher(TOPIC) for _ in range(publishers)]
    total = publishers * count
    try:
        for publisher in publishers_list:
            await publisher.register()
        for seq in range(count):
            for index, publisher in enumerate(publishers_list, start=1):
                payload = {"from": f"pub-{index}", "seq": seq}
                await publisher.publish(payload)
    finally:
        await bus.stop()

    sources = tuple(sorted({item["from"] for item in received}))
    return ScenarioResult(
        "Nv1",
        total,
        {"sub-1": len(received)},
        sources,
    )


def _is_pass(
    result: ScenarioResult,
    expected_delivered: int,
    expected_sources: Tuple[str, ...] = (),
) -> bool:
    if any(value != expected_delivered for value in result.delivered.values()):
        return False
    if expected_sources:
        return result.sources == expected_sources
    return True


async def run_all(
    *, count: int, subscribers: int, publishers: int
) -> list[ScenarioResult]:
    return [
        await run_one_to_one(count),
        await run_one_to_many(subscribers, count),
        await run_many_to_one(publishers, count),
    ]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="tinySOA local pub/sub topology scenarios"
    )
    parser.add_argument(
        "--scenario",
        choices=["1v1", "1vn", "nv1", "all"],
        default="all",
        help="which topology to run (default: all)",
    )
    parser.add_argument(
        "--count", type=int, default=3, help="messages per publisher (default: 3)"
    )
    parser.add_argument(
        "--subscribers", type=int, default=3, help="1vN subscriber count (default: 3)"
    )
    parser.add_argument(
        "--publishers", type=int, default=3, help="Nv1 publisher count (default: 3)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=LOG_LEVELS,
        help="logging verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("local.topologies")

    if args.count <= 0 or args.subscribers <= 0 or args.publishers <= 0:
        logger.error("count/subscribers/publishers must be positive")
        return 2

    if args.scenario == "all":
        results = await run_all(
            count=args.count,
            subscribers=args.subscribers,
            publishers=args.publishers,
        )
    elif args.scenario == "1v1":
        results = [await run_one_to_one(args.count)]
    elif args.scenario == "1vn":
        results = [await run_one_to_many(args.subscribers, args.count)]
    else:
        results = [await run_many_to_one(args.publishers, args.count)]

    ok = True
    for result in results:
        if result.name == "Nv1":
            expected_delivered = args.publishers * args.count
            expected_sources = tuple(f"pub-{i}" for i in range(1, args.publishers + 1))
        else:
            expected_delivered = args.count
            expected_sources = ()
        passed = _is_pass(result, expected_delivered, expected_sources)
        ok = ok and passed
        logger.info(
            "%s published=%d delivered=%s sources=%s => %s",
            result.name,
            result.published,
            result.delivered,
            result.sources,
            "PASS" if passed else "FAIL",
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
