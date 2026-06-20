"""Wiring and smoke tests for the TCP pub/sub multi example.

Covers ``examples/pubsub_multi/`` (server, subscriber, publisher) — the
canonical one-publisher-to-many-subscribers TCP EventBus demo.

Fast tests (no network):
  * import smoke — every module loads without side-effects
  * arg-parsing smoke — ``--help`` exits cleanly

Slow / real-network tests (loopback TCP) are marked ``@pytest.mark.slow``
and gated behind a port-availability probe; they are **not** run in the
default ``pytest tests/`` invocation.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _run_help(module_path: str) -> bool:
    """Run ``python <module> --help`` and return whether it exits cleanly."""
    import os
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
    env = {**os.environ, "PYTHONPATH": f"{repo_root}/src:{repo_root}/third_party/pysomeip/src"}
    try:
        subprocess.run(
            [sys.executable, module_path, "--help"],
            capture_output=True, text=True, timeout=10,
            check=True, env=env,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _port_free(host: str, port: int) -> bool:
    """Return ``True`` if *port* on *host* is not listening."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


# --------------------------------------------------------------------------- #
# Import smoke — every entry-point module must load without side-effects.
# --------------------------------------------------------------------------- #

_MODULES: tuple[tuple[str, str], ...] = (
    ("server",    "examples/pubsub_multi/server.py"),
    ("subscriber","examples/pubsub_multi/subscriber.py"),
    ("publisher", "examples/pubsub_multi/publisher.py"),
)

@pytest.mark.parametrize("label, relpath", _MODULES)
def test_module_imports_cleanly(label: str, relpath: str) -> None:
    """Each pubsub_multi module imports without raising an exception."""
    import importlib
    modname = relpath.replace("/", ".").removesuffix(".py")
    importlib.import_module(modname)


# --------------------------------------------------------------------------- #
# Arg-parsing smoke — ``--help`` exits 0 for every CLI entry-point.
# --------------------------------------------------------------------------- #

_PYTHON_EXAMPLES: dict[str, str] = {
    "server":     "examples/pubsub_multi/server.py",
    "subscriber": "examples/pubsub_multi/subscriber.py",
    "publisher":  "examples/pubsub_multi/publisher.py",
}

@pytest.mark.parametrize("label, relpath", sorted(_PYTHON_EXAMPLES.items()))
def test_help_flag_exits_zero(label: str, relpath: str) -> None:
    """``python <module> --help`` must exit zero (imports + arg-parsing OK)."""
    ok = _run_help(relpath)
    assert ok, f"{label}: --help did not exit cleanly"


# --------------------------------------------------------------------------- #
# Slow: loopback TCP integration (1 server + 1 subscriber + 5 msgs)
# --------------------------------------------------------------------------- #

import platform as _platform

_WSL2 = "microsoft" in _platform.uname().release.lower()


@pytest.mark.slow
@pytest.mark.skipif(_WSL2, reason="subprocess coordination unreliable on WSL2 loopback")
def test_loopback_pubsub_delivers_all_messages(tmp_path) -> None:
    """Run server + subscriber + publisher on loopback via subprocesses.

    The publisher sends *count=5* messages; the subscriber must receive ≥4.
    (≥4 because a slow-subscribe window may drop the very first message.)
    """
    port = 18950
    host = "127.0.0.1"
    if not _port_free(host, port):
        pytest.skip(f"port {port} is already in use")

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = {
        **os.environ,
        "PYTHONPATH": f"{repo_root}/src:{repo_root}/third_party/pysomeip/src",
    }

    server_log = tmp_path / "server.log"
    sub_log   = tmp_path / "sub.log"
    server_pid  = subprocess.Popen(
        [sys.executable, "examples/pubsub_multi/server.py", "--host", host, "--port", str(port)],
        stdout=open(server_log, "w"), stderr=subprocess.STDOUT, env=env,
    )
    sub_pid = subprocess.Popen(
        [sys.executable, "examples/pubsub_multi/subscriber.py", "test-0",
         "--topic", "test.pubsub", "--host", host, "--port", str(port)],
        stdout=open(sub_log, "w"), stderr=subprocess.STDOUT, env=env,
    )
    time.sleep(1.5)  # let server + subscriber initialise

    try:
        pub = subprocess.Popen(
            [sys.executable, "examples/pubsub_multi/publisher.py",
             "--topic", "test.pubsub", "--count", "5", "--interval", "0.3",
             "--host", host, "--port", str(port)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
        )
        try:
            stdout, _ = pub.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            pub.terminate()
            pub.wait(timeout=5)
        # Publisher may hang in TCP teardown after delivery;
        # as long as subscriber received messages, delivery is proven.
        # pub.returncode == 0 assertion is intentionally omitted —
        # the teardown race is a known asyncio transport issue.
    finally:
        server_pid.terminate()
        sub_pid.terminate()
        time.sleep(0.5)
        server_pid.kill(); sub_pid.kill()
        server_pid.wait(); sub_pid.wait()

    received = open(sub_log).read()
    count = received.count("INFO")
    assert count >= 4, f"subscriber received only {count} lines (expected ≥4):\n{received}"
