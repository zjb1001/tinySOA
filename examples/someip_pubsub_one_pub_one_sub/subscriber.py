"""SOME/IP one-to-one subscriber."""

from __future__ import annotations

import argparse
import asyncio
import logging

from tinysoa.eventbus import EventMessage, SomeIPService

from .service_contract import (
    EVENT_MAPPINGS,
    SERVICE_ID,
    SUBSCRIBER_PORT,
    TOPIC,
    subscriber_config,
)

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
logger = logging.getLogger("someip.one_to_one.subscriber")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="tinySOA SOME/IP one-to-one subscriber"
    )
    parser.add_argument(
        "--want", type=int, default=3, help="events to receive before stopping"
    )
    parser.add_argument(
        "--timeout", type=float, default=40.0, help="max seconds to wait"
    )
    parser.add_argument(
        "--local-port",
        type=int,
        default=SUBSCRIBER_PORT,
        help="local port base for the subscriber process",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=LOG_LEVELS,
        help="logging verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


async def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s.%(msecs)03d | SUBSCRIBER | %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.want <= 0:
        logger.error("--want must be positive")
        return 2

    # Pure config: no socket or SD endpoint exists yet.
    config = subscriber_config(args.local_port)
    service = SomeIPService(
        config,
        event_mappings=EVENT_MAPPINGS,
        is_publisher=False,
    )
    logger.info(
        "starting service=0x%04x topic=%s want=%d timeout=%.0fs",
        SERVICE_ID,
        TOPIC,
        args.want,
        args.timeout,
    )
    # start() creates the endpoint, binds ports, and starts SD.
    await service.start()

    received: list[dict] = []
    done = asyncio.Event()

    async def on_event(message: EventMessage) -> None:
        payload = message.payload if isinstance(message.payload, dict) else {}
        received.append(payload)
        logger.info("RECEIVED seq=%s", payload.get("seq"))
        if len(received) >= args.want:
            done.set()

    subscriber = service.subscriber(TOPIC, on_event)
    # register() starts SD FindSubscribe and binds the handler.
    await service.register(subscriber)
    try:
        await asyncio.wait_for(done.wait(), timeout=args.timeout)
        logger.info("SUCCESS received %d/%d", len(received), args.want)
        return 0
    except asyncio.TimeoutError:
        logger.warning("TIMEOUT received %d/%d", len(received), args.want)
        return 1
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(0) from None
