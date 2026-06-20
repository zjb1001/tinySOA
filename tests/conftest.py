"""Shared pytest configuration and fixtures for tinySOA tests.

Fixtures defined here are auto-discovered by pytest and available to all
test files under ``tests/``.
"""
from __future__ import annotations

import socket

import pytest


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (real network / subprocess); "
        "deselect with: -m 'not slow'",
    )


def port_free(host: str, port: int) -> bool:
    """Return ``True`` if *port* on *host* is not listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


# tests/system/ holds standalone scripts, not pytest test modules.
collect_ignore_glob = ["system/*"]
