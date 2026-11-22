"""SOME/IP multi-publisher demo — shared configuration.

Single source of truth for the three sensor services (temperature / humidity /
pressure): their SOME/IP identity (service / instance / eventgroup ids), the
tinySOA topic, the unicast port base, the payload shape and the sampling
cadence. The three publisher scripts and the aggregator subscriber all import
from here so the topic <-> service-id <-> port mapping can never drift between
them.

Run convention (set ``PYTHONPATH`` so both ``someip`` and ``tinysoa`` resolve
from source; run each script from this directory):

    export PYTHONPATH=$REPO/src:$REPO/tinySOA/src
    python -m examples.someip_pubsub_many_pubs_one_sub.publisher1_temperature     # or publisher2/3, subscriber_aggregator
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from tinysoa.eventbus import SomeIPServiceBinding, SomeIPTopicMapping

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
    error.
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

    @property
    def binding(self) -> SomeIPServiceBinding:
        """The service binding used by the publisher process."""
        return SomeIPServiceBinding(
            name=self.key,
            service_id=self.service_id,
            instance_id=INSTANCE_ID,
            methods={},
            major_version=MAJOR_VERSION,
            local_ip=LOCAL_IP,
            server_port=self.publisher_port,
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
SENSOR_MAPPINGS: Dict[str, SomeIPTopicMapping] = {
    s.topic: s.mapping for s in SENSORS.values()
}
