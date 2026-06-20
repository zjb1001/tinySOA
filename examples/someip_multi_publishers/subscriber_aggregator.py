#!/usr/bin/env python3
"""SOME/IP multi-publisher aggregator subscriber (engineering-grade).

Discovers all three sensor publishers (temperature / humidity / pressure) via
SOME/IP Service Discovery, subscribes to their topics, and renders a unified
dashboard once a full set of readings has arrived.

Run (``PYTHONPATH`` set so both ``someip`` and ``tinysoa`` resolve; from this
directory):

    export PYTHONPATH=$REPO/src:$REPO/tinySOA/src
    python subscriber_aggregator.py                       # run forever
    python subscriber_aggregator.py --count 9             # stop after 9 readings

Exit code 0 on clean shutdown.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from typing import Awaitable, Callable, Dict, List

from tinysoa.eventbus.message import EventMessage
from tinysoa.eventbus.someip import SomeIPEventBus

from _common import (
    LOCAL_IP,
    LOG_LEVELS,
    SENSORS,
    SENSOR_MAPPINGS,
    SensorSpec,
    configure_logging,
    install_quiet_teardown,
)

logger = logging.getLogger("someip.demo.aggregator")

#: Default unicast port base for the subscriber process (must differ from the
#: publishers' 30500-30502 so each process owns distinct ports).
DEFAULT_SUBSCRIBER_PORT = 30510


class SensorAggregator:
    """Aggregate the latest reading from every sensor into one dashboard."""

    def __init__(self, specs: Dict[str, SensorSpec]) -> None:
        self._specs = specs
        self.latest: Dict[str, dict] = {}
        self.counts: Dict[str, int] = defaultdict(int)

    def total_readings(self) -> int:
        return sum(self.counts.values())

    def make_handler(self, key: str) -> Callable[[EventMessage], Awaitable[None]]:
        """Build the async handler for one sensor topic (closes over ``key``)."""
        spec = self._specs[key]

        async def on_reading(msg: EventMessage) -> None:
            payload = msg.payload if isinstance(msg.payload, dict) else {"raw": msg.payload}
            self.latest[key] = payload
            self.counts[key] += 1
            logger.info(
                "received %s (service 0x%04x, port %d): value=%s unit=%s sensor=%s",
                key,
                spec.service_id,
                spec.publisher_port,
                payload.get("value"),
                payload.get("unit"),
                payload.get("sensor_id"),
            )
            self._render_dashboard()

        return on_reading

    def _render_dashboard(self) -> None:
        """Log a combined dashboard once a full reading set is available."""
        if len(self.latest) < len(self._specs):
            return
        lines = ["", "=" * 64, "SENSOR DASHBOARD".center(64), "=" * 64]
        for key, spec in self._specs.items():
            data = self.latest[key]
            lines.append(
                f"  {spec.name:<20} {data.get('value')} {spec.unit:<8} "
                f"(service 0x{spec.service_id:04x})"
            )
        counts = ", ".join(f"{k}={v}" for k, v in self.counts.items())
        lines.extend(["-" * 64, f"  readings: {counts}", "=" * 64])
        logger.info("\n".join(lines))


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA SOME/IP sensor aggregator subscriber")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_SUBSCRIBER_PORT, help="subscriber unicast port base"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="total readings before stopping; 0 = forever (default: 0)",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=LOG_LEVELS, help="logging verbosity (default: INFO)"
    )
    return parser.parse_args(argv)


async def main(argv=None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    install_quiet_teardown()

    # is_publisher=False: discovery-only — do not advertise; let the real
    # publishers announce their services so SD finds them, not us.
    bus = SomeIPEventBus(SENSOR_MAPPINGS, local_ip=LOCAL_IP, publisher_port=args.port, is_publisher=False)
    aggregator = SensorAggregator(SENSORS)
    subscriptions: List = []

    logger.info("starting aggregator on %s, port base %d", LOCAL_IP, args.port)
    await bus.start()
    logger.info("SOME/IP stack initialized; discovering sensors via SD...")

    for key, spec in SENSORS.items():
        sub = bus.subscribe(spec.topic, aggregator.make_handler(key))
        subscriptions.append(sub)
        logger.info("subscribed to %s (service 0x%04x)", spec.topic, spec.service_id)

    try:
        while args.count <= 0 or aggregator.total_readings() < args.count:
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("shutdown signal received")
    finally:
        logger.info("cleaning up subscriptions...")
        for sub in subscriptions:
            bus.unsubscribe(sub)
        await bus.stop()
        logger.info("aggregator stopped after %d total reading(s)", aggregator.total_readings())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
