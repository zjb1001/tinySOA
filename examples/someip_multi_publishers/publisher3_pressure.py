#!/usr/bin/env python3
"""SOME/IP pressure sensor publisher (engineering-grade).

Periodically publishes simulated atmospheric-pressure readings on the
``sensor.pressure`` topic via a SOME/IP EventGroup, advertising the service
through Service Discovery so the aggregator subscriber can find it.

Run (``PYTHONPATH`` set so both ``someip`` and ``tinysoa`` resolve; from this
directory):

    export PYTHONPATH=$REPO/src:$REPO/tinySOA/src
    python publisher3_pressure.py                 # run forever
    python publisher3_pressure.py --count 5       # bounded (CI-friendly)

Exit code 0 on clean shutdown.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from _common import LOG_LEVELS, SENSORS, run_sensor_publisher


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tinySOA SOME/IP pressure publisher")
    parser.add_argument(
        "--count", type=int, default=0, help="samples to send; 0 = forever (default: 0)"
    )
    parser.add_argument(
        "--interval", type=float, default=None, help="seconds between samples (default: spec)"
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=LOG_LEVELS, help="logging verbosity (default: INFO)"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        asyncio.run(
            run_sensor_publisher(
                SENSORS["pressure"],
                count=args.count,
                interval=args.interval,
                log_level=args.log_level,
            )
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
