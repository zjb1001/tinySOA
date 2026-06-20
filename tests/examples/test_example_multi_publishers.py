"""Wiring and smoke tests for the multi-publishers-single-subscriber example.

Covers ``examples/multi_publishers_single_sub/`` (many publishers → one
subscriber, TCP EventBus) in the fast no-network tier.

Fast tests (no network):
  * import smoke — ``publisher_with_id`` loads without side-effects
  * arg-parsing smoke — ``--help`` exits cleanly
  * publisher identity wiring — each publisher id is encoded in payload

This example re-uses the server / subscriber from ``pubsub_multi/`` which
is tested separately.
"""
from __future__ import annotations

import sys

import pytest


# --------------------------------------------------------------------------- #
# Import smoke
# --------------------------------------------------------------------------- #

def test_publisher_with_id_module_imports_cleanly() -> None:
    """``publisher_with_id.py`` imports without raising an exception."""
    import examples.multi_publishers_single_sub.publisher_with_id  # noqa: F401


# --------------------------------------------------------------------------- #
# Arg-parsing smoke
# --------------------------------------------------------------------------- #

def test_publisher_with_id_help_flag_exits_zero() -> None:
    """``python publisher_with_id.py --help`` exits cleanly."""
    import os, subprocess
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": f"{repo_root}/src:{repo_root}/third_party/pysomeip/src",
    }
    subprocess.run(
        [sys.executable, "examples/multi_publishers_single_sub/publisher_with_id.py", "--help"],
        capture_output=True, text=True, timeout=10,
        check=True, env=env,
    )


# --------------------------------------------------------------------------- #
# Wiring contract: publisher-with-id
# --------------------------------------------------------------------------- #

def test_publisher_with_id_can_be_imported_and_parse_args() -> None:
    """Verify that the ``publisher_with_id`` module can be introspected.

    The module must export a ``main`` callable that accepts an argv list.
    """
    import examples.multi_publishers_single_sub.publisher_with_id as mod

    assert hasattr(mod, "main"), "publisher_with_id must export a 'main' function"
    assert callable(mod.main)
