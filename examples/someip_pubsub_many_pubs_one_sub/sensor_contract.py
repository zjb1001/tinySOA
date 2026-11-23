"""Shared sensor service contract for the multi-publisher demo.

Single source of truth for the three sensor services (temperature / humidity /
pressure): their SOME/IP identity, tinySOA topic, unicast port base, payload
shape, and sampling cadence.  The publisher scripts and the aggregator all
import this contract so the topic <-> service-id <-> port mapping cannot drift.
"""

from __future__ import annotations

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
    def publisher_config(self) -> SomeIPServiceBinding:
        """Publisher endpoint for this sensor service."""
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
