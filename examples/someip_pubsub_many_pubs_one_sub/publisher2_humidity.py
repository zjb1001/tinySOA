#!/usr/bin/env python3
"""SOME/IP humidity sensor publisher.

Publishes simulated humidity readings on ``sensor.humidity`` through a SOME/IP
EventGroup and advertises the service via SD.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from tinysoa.eventbus import SomeIPService

from .demo_support import LOG_LEVELS, configure_logging, install_quiet_teardown
from .sensor_contract import INSTANCE_ID, SENSORS


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA SOME/IP humidity publisher")
    parser.add_argument(
        "--count", type=int, default=0, help="samples to send; 0 = forever (default: 0)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="seconds between samples (default: spec)",
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
    spec = SENSORS["humidity"]
    log = configure_logging(args.log_level, name=f"someip.demo.{spec.key}")
    install_quiet_teardown()
    period = spec.interval if args.interval is None else args.interval

    service = SomeIPService(
        spec.publisher_config,
        event_mappings={spec.topic: spec.mapping},
        is_publisher=True,
    )
    publisher = service.publisher(spec.topic)

    log.info(
        "starting %s (service 0x%04x, instance 0x%04x, port %d)",
        spec.name,
        spec.service_id,
        INSTANCE_ID,
        spec.publisher_port,
    )
    await service.start()
    await service.register(publisher)
    log.info("SOME/IP stack initialized; waiting for subscribers via SD...")

    sent = 0
    try:
        while args.count <= 0 or sent < args.count:
            value = spec.sample()
            payload = {
                "value": round(value, spec.decimals),
                "unit": spec.unit,
                "sensor_id": spec.sensor_id,
                "location": spec.location,
            }
            await publisher.publish(payload)
            log.info("published %s: %.2f %s", spec.key, value, spec.unit)
            sent += 1
            await asyncio.sleep(period)
    except KeyboardInterrupt:
        log.info("shutdown signal received")
    except Exception as exc:  # noqa: BLE001 - demo surfaces any publisher failure
        log.error("publisher error: %s", exc, exc_info=True)
    finally:
        log.info("stopping %s...", spec.name)
        await service.stop()
        log.info("%s stopped after %d sample(s)", spec.name, sent)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
