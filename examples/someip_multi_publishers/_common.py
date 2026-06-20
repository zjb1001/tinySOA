"""SOME/IP multi-publisher demo — shared configuration and runtime helpers.

Single source of truth for the three sensor services (temperature / humidity /
pressure): their SOME/IP identity (service / instance / eventgroup ids), the
tinySOA topic, the unicast port base, the payload shape and the sampling
cadence. The three publisher scripts and the aggregator subscriber all import
from here so the topic <-> service-id <-> port mapping can never drift between
them.

Run convention (set ``PYTHONPATH`` so both ``someip`` and ``tinysoa`` resolve
from source; run each script from this directory):

    export PYTHONPATH=$REPO/src:$REPO/tinySOA/src
    python publisher1_temperature.py     # or publisher2/3, subscriber_aggregator
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from tinysoa.eventbus.message import EventMessage
from tinysoa.eventbus.someip import SomeIPEventBus, SomeIPTopicMapping

# Loopback address used by every process in this demo.
LOCAL_IP = "127.0.0.1"

# SOME/IP identity shared by every sensor service in this demo.
INSTANCE_ID = 0x0001
EVENTGROUP_ID = 0x0001
MAJOR_VERSION = 1

_LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

#: Valid logging level tokens accepted on the CLI.
LOG_LEVELS: Tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")


def configure_logging(level: str = "INFO", name: str = "someip.demo") -> logging.Logger:
    """Configure root logging once and return a named logger."""
    logging.basicConfig(level=level, format=_LOG_FORMAT, datefmt=_LOG_DATEFMT)
    return logging.getLogger(name)


def install_quiet_teardown() -> None:
    """Silence benign teardown races in the underlying SOME/IP stack.

    When ``SomeIPEventBus.stop()`` closes the SD transports, two kinds of
    post-delivery noise can surface (delivery has already succeeded by then):

    * an in-flight periodic ``sendto`` touching the loop after shutdown begins,
      raising ``AttributeError: 'NoneType' object has no attribute
      'call_exception_handler'``;
    * the SD announcer's ``connection_lost`` double-stopping an already-stopped
      task, raising ``RuntimeError: task already stopped``.

    Both originate in the pysomeip SD layer during teardown only. Install this
    handler to drop just those two messages while still logging every real
    error. (Extends ``examples/cross_process_someip/__init__.py``.)
    """
    loop = asyncio.get_running_loop()

    def _handler(loop, context) -> None:  # type: ignore[no-untyped-def]
        exc = context.get("exception")
        if exc is not None:
            message = str(exc)
            if "call_exception_handler" in message or "task already stopped" in message:
                return
        loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)


@dataclass(frozen=True)
class SensorSpec:
    """Declarative description of one sensor publisher."""

    key: str
    name: str
    topic: str
    service_id: int
    publisher_port: int
    unit: str
    sensor_id: str
    location: str = "Room A"
    base_value: float = 0.0
    jitter: float = 0.0
    interval: float = 1.0
    decimals: int = 2
    clamp: Optional[Tuple[float, float]] = None

    def sample(self) -> float:
        """Produce one noisy reading around ``base_value`` (clamped if set)."""
        value = self.base_value + random.uniform(-self.jitter, self.jitter)
        if self.clamp is not None:
            low, high = self.clamp
            value = max(low, min(high, value))
        return value

    @property
    def mapping(self) -> SomeIPTopicMapping:
        """The SOME/IP identity for this sensor's topic."""
        return SomeIPTopicMapping(
            service_id=self.service_id,
            instance_id=INSTANCE_ID,
            eventgroup_id=EVENTGROUP_ID,
            major_version=MAJOR_VERSION,
        )


#: Every sensor in the demo, keyed by a short identifier.
SENSORS: Dict[str, SensorSpec] = {
    "temperature": SensorSpec(
        key="temperature",
        name="Temperature Sensor",
        topic="sensor.temperature",
        service_id=0x1001,
        publisher_port=30500,
        unit="celsius",
        sensor_id="TEMP_001",
        base_value=20.0,
        jitter=0.5,
        interval=1.0,
    ),
    "humidity": SensorSpec(
        key="humidity",
        name="Humidity Sensor",
        topic="sensor.humidity",
        service_id=0x1002,
        publisher_port=30501,
        unit="percent",
        sensor_id="HUM_001",
        base_value=65.0,
        jitter=5.0,
        interval=1.2,
        decimals=1,
        clamp=(0.0, 100.0),
    ),
    "pressure": SensorSpec(
        key="pressure",
        name="Pressure Sensor",
        topic="sensor.pressure",
        service_id=0x1003,
        publisher_port=30502,
        unit="hPa",
        sensor_id="PRESS_001",
        base_value=1013.25,
        jitter=2.0,
        interval=1.5,
    ),
}

#: topic -> SOME/IP mapping for EVERY sensor; the aggregator subscribes to all.
SENSOR_MAPPINGS: Dict[str, SomeIPTopicMapping] = {s.topic: s.mapping for s in SENSORS.values()}


async def run_sensor_publisher(
    spec: SensorSpec,
    *,
    count: int = 0,
    interval: Optional[float] = None,
    log_level: str = "INFO",
) -> int:
    """Publish ``spec`` sensor readings via SOME/IP until interrupted or done.

    Args:
        spec: which sensor to emulate.
        count: samples to send; ``<= 0`` means run forever (until SIGINT).
        interval: override the spec's default cadence (seconds).
        log_level: logging verbosity.

    Returns:
        The number of samples actually published.
    """
    logger = configure_logging(log_level, name=f"someip.demo.{spec.key}")
    install_quiet_teardown()

    mappings = {spec.topic: spec.mapping}
    # is_publisher defaults to True -> this process advertises the service via SD.
    bus = SomeIPEventBus(mappings, local_ip=LOCAL_IP, publisher_port=spec.publisher_port)
    period = spec.interval if interval is None else interval

    logger.info(
        "starting %s (service 0x%04x, instance 0x%04x, port %d)",
        spec.name,
        spec.service_id,
        INSTANCE_ID,
        spec.publisher_port,
    )
    await bus.start()
    logger.info("SOME/IP stack initialized; waiting for subscribers via SD...")

    sent = 0
    try:
        while count <= 0 or sent < count:
            value = spec.sample()
            await bus.publish(
                EventMessage(
                    topic=spec.topic,
                    payload={
                        "value": round(value, spec.decimals),
                        "unit": spec.unit,
                        "sensor_id": spec.sensor_id,
                        "location": spec.location,
                    },
                )
            )
            logger.info("published %s: %.2f %s", spec.key, value, spec.unit)
            sent += 1
            await asyncio.sleep(period)
    except KeyboardInterrupt:
        logger.info("shutdown signal received")
    except Exception as exc:  # noqa: BLE001 - demo surfaces any publisher failure
        logger.error("publisher error: %s", exc, exc_info=True)
    finally:
        logger.info("stopping %s...", spec.name)
        await bus.stop()
        logger.info("%s stopped after %d sample(s)", spec.name, sent)
    return sent
