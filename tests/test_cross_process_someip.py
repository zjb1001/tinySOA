"""
Tests for the cross-process SOME/IP pub/sub example.

Two test classes:

* ``TestExampleWiring`` — fast, no network. Verifies the example's topic↔SOME/IP
  mapping is internally consistent and the publisher/subscriber modules import
  cleanly against the EventBus ABC.
* ``TestCrossProcessDelivery`` — slow, real network on loopback. Spawns the
  stdlib orchestrator, which in turn launches the publisher and subscriber as
  two SEPARATE OS processes and asserts the subscriber received events the
  publisher sent — proving the "different processes" constraint through the
  SOME/IP EventBus (pysomeip stack).

Run:

    PYTHONPATH=../src:src python -m pytest tests/test_cross_process_someip.py -q

(Use ``-m 'not slow'`` to skip the real-network integration test.)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# tinySOA/tests/test_cross_process_someip.py  ->  parents[1] = tinySOA/
TINYSOA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TINYSOA_DIR.parent
EXAMPLE_DIR = TINYSOA_DIR / "examples" / "cross_process_someip"
ORCHESTRATOR = EXAMPLE_DIR / "run_cross_process.py"

# Make both `someip` (pysomeip, repo/src) and `tinysoa` (tinySOA/src) importable
# from source without installing anything, and let `examples.*` resolve too.
for _p in (str(REPO_ROOT / "src"), str(TINYSOA_DIR / "src"), str(TINYSOA_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# --------------------------------------------------------------------------- #
# Fast, no-network: example wiring is consistent and import-clean.
# --------------------------------------------------------------------------- #
class TestExampleWiring:
    def test_mapping_resolves_topic_to_someip_identity(self) -> None:
        from examples.cross_process_someip import (
            EVENTGROUP_ID,
            INSTANCE_ID,
            MAPPING,
            MAPPINGS,
            SERVICE_ID,
            TOPIC,
        )

        assert TOPIC in MAPPINGS
        assert MAPPINGS[TOPIC] is MAPPING
        assert MAPPING.service_id == SERVICE_ID
        assert MAPPING.instance_id == INSTANCE_ID
        assert MAPPING.eventgroup_id == EVENTGROUP_ID

    def test_someip_eventbus_satisfies_eventbus_contract(self) -> None:
        from tinysoa.eventbus.bus import EventBus
        from tinysoa.eventbus.someip import SomeIPEventBus

        # The class implements the ABC's four abstract methods.
        assert issubclass(SomeIPEventBus, EventBus)
        remaining = getattr(SomeIPEventBus, "__abstractmethods__", set())
        assert not remaining, f"unimplemented abstract methods: {remaining}"

    def test_publisher_and_subscriber_modules_import(self) -> None:
        import importlib

        for mod in (
            "examples.cross_process_someip.publisher",
            "examples.cross_process_someip.subscriber",
            "examples.cross_process_someip.run_cross_process",
        ):
            importlib.import_module(mod)  # must not raise


# --------------------------------------------------------------------------- #
# Slow, real-network: cross-process delivery through the SOME/IP EventBus.
# --------------------------------------------------------------------------- #
@pytest.mark.slow
class TestCrossProcessDelivery:
    @pytest.mark.skipif(not ORCHESTRATOR.exists(), reason="orchestrator script missing")
    def test_two_processes_exchange_events_via_someip_eventbus(self) -> None:
        """The subscriber PROCESS receives events the publisher PROCESS sent.

        Both are real OS subprocesses launched by the orchestrator; they share
        no memory and communicate only over SOME/IP (pysomeip SD + unicast
        notifications) on loopback.
        """
        proc = subprocess.run(
            [sys.executable, str(ORCHESTRATOR)],
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        assert proc.returncode == 0, f"orchestrator failed (rc={proc.returncode}):\n{out}"
        assert "RESULT:" in out and "PASS" in out, f"unexpected output:\n{out}"
        assert "received=3/3" in out, f"subscriber did not collect 3 events:\n{out}"
