"""Shared pytest configuration for tinySOA tests."""
from __future__ import annotations


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (real network / subprocess); "
        "deselect with: -m 'not slow'",
    )
