"""Wiring and configuration-consistency tests for the SOME/IP multi-publisher
example.

Covers ``examples/someip_multi_publishers/`` (three sensor publishers +
aggregator subscriber, communicating over SOME/IP with pysomeip).

Fast tests (no network, no SOME/IP stack — pure config validation):
  * module import smoke
  * SENSORS data integrity (unique service_ids, unique ports, every sensor
    has a valid ``SomeIPTopicMapping``)
  * SENSOR_MAPPINGS consistency (each topic ↔ correct sensor's mapping)

Slow / real-network tests are SKIPPED by default (SD multicast is known to
be saturated in the current development environment).  Remove the skip
decorator to run them on a clean loopback.
"""
from __future__ import annotations

import sys

import pytest


# --------------------------------------------------------------------------- #
# Fast: import smoke — all entry-point modules load cleanly.
# --------------------------------------------------------------------------- #

_SOMEIP_EXAMPLE_MODS: tuple[str, ...] = (
    "examples.someip_multi_publishers._common",
    "examples.someip_multi_publishers.publisher1_temperature",
    "examples.someip_multi_publishers.publisher2_humidity",
    "examples.someip_multi_publishers.publisher3_pressure",
    "examples.someip_multi_publishers.subscriber_aggregator",
)

# Importable-import modules import ``from _common import ...`` (bare local).
# Add the example dir to ``sys.path`` once so those relative imports resolve.
_SOMEIP_EXAMPLE_DIR = str(
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "examples" / "someip_multi_publishers"
)
if _SOMEIP_EXAMPLE_DIR not in sys.path:
    sys.path.insert(0, _SOMEIP_EXAMPLE_DIR)


@pytest.mark.parametrize("modname", sorted(_SOMEIP_EXAMPLE_MODS))
def test_someip_example_module_imports_cleanly(modname: str) -> None:
    """Every SOME/IP example module imports without raising an exception."""
    import importlib
    importlib.import_module(modname)


# --------------------------------------------------------------------------- #
# Fast: wiring / configuration consistency for SENSORS & SENSOR_MAPPINGS.
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def _common() -> object:
    """Load ``_common`` once for the configuration-consistency tests."""
    from examples.someip_multi_publishers import _common as mod
    return mod


class TestSensorConfigIntegrity:
    """Each sensor's configuration must be internally consistent."""

    def test_service_ids_are_unique(self, _common) -> None:
        ids = [s.service_id for s in _common.SENSORS.values()]
        assert len(ids) == len(set(ids)), f"duplicate service_ids: {ids}"

    def test_publisher_ports_are_unique(self, _common) -> None:
        ports = [s.publisher_port for s in _common.SENSORS.values()]
        assert len(ports) == len(set(ports)), f"duplicate ports: {ports}"

    def test_every_sensor_has_valid_mapping(self, _common) -> None:
        from tinysoa.eventbus.someip import SomeIPTopicMapping
        for key, sensor in _common.SENSORS.items():
            assert isinstance(sensor.mapping, SomeIPTopicMapping), (
                f"{key}: mapping is not a SomeIPTopicMapping"
            )

    @pytest.mark.parametrize("key", sorted(("temperature", "humidity", "pressure")))
    def test_sensor_has_required_fields(self, _common, key: str) -> None:
        sensor = _common.SENSORS[key]
        assert sensor.service_id  > 0
        assert sensor.publisher_port > 0
        assert sensor.topic
        assert sensor.unit


class TestTopicMappingConsistency:
    """SENSOR_MAPPINGS must map topic → the matching sensor's identity."""

    def test_mapping_count_matches_sensors(self, _common) -> None:
        assert len(_common.SENSOR_MAPPINGS) == len(_common.SENSORS)

    def test_each_topic_points_to_correct_service_id(self, _common) -> None:
        for key, sensor in _common.SENSORS.items():
            mapping = _common.SENSOR_MAPPINGS[sensor.topic]
            assert mapping.service_id    == sensor.service_id
            assert mapping.instance_id   == 0x0001

    def test_instance_and_eventgroup_id_are_consistent(self, _common) -> None:
        from examples.someip_multi_publishers._common import EVENTGROUP_ID, INSTANCE_ID
        for mapping in _common.SENSOR_MAPPINGS.values():
            assert mapping.instance_id   == INSTANCE_ID
            assert mapping.eventgroup_id == EVENTGROUP_ID


# --------------------------------------------------------------------------- #
# Slow: real-network SOME/IP integration (SD + unicast event delivery).
#                                                                  SKIPPED
# The current development environment has ~6 pre-existing SOME/IP      by
# processes saturating the SD multicast group (224.224.224.245:30490), default
# rendering real-network delivery unreliable.  Remove the skip
# decorators and ensure no other SOME/IP participants are active
# before running these.
# --------------------------------------------------------------------------- #

import platform as _platform

_WSL2 = "microsoft" in _platform.uname().release.lower()


@pytest.mark.slow
@pytest.mark.skipif(_WSL2, reason="SOME/IP SD delivery not reliable on WSL2 loopback")
class TestSomeIPSensorDelivery:
    """Full delivery: 1 publisher → aggregator over real SOME/IP on loopback."""

    def test_one_publisher_delivers_to_aggregator(self) -> None:
        """Temperature publisher (3 samples) should be received by aggregator."""
        import subprocess, sys, tempfile, time
        with tempfile.TemporaryDirectory() as td:
            pub_log = f"{td}/pub.log"; sub_log = f"{td}/sub.log"
            pub = subprocess.Popen(
                [sys.executable,
                 "examples/someip_multi_publishers/publisher1_temperature.py",
                 "--count", "3", "--interval", "0.5"],
                stdout=open(pub_log, "w"), stderr=subprocess.STDOUT,
                cwd="examples/someip_multi_publishers",
            )
            time.sleep(1.5)  # let SD offer propagate
            sub = subprocess.Popen(
                [sys.executable,
                 "examples/someip_multi_publishers/subscriber_aggregator.py",
                 "--count", "3"],
                stdout=open(sub_log, "w"), stderr=subprocess.STDOUT,
                cwd="examples/someip_multi_publishers",
            )
            try:
                sub.wait(timeout=40)
            finally:
                pub.terminate(); pub.wait(timeout=5)
            out = open(sub_log).read()
            assert "aggregator stopped after" in out
            assert "received" in out.lower()
