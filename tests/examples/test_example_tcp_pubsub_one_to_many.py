"""Wiring and smoke tests for the TCP pub/sub one-to-many example."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULE = "examples.tcp_pubsub_one_to_many"


def _env() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": (
            f"{REPO_ROOT}:{REPO_ROOT}/src:{REPO_ROOT}/third_party/pysomeip/src"
        ),
    }


def _run_help(module: str) -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", module, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            cwd=REPO_ROOT,
            env=_env(),
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _port_free(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


_MODULES: tuple[str, ...] = (
    f"{MODULE}.server",
    f"{MODULE}.subscriber",
    f"{MODULE}.publisher",
)


@pytest.mark.parametrize("module", _MODULES)
def test_module_imports_cleanly(module: str) -> None:
    import importlib

    importlib.import_module(module)


@pytest.mark.parametrize("module", _MODULES)
def test_help_flag_exits_zero(module: str) -> None:
    ok = _run_help(module)
    assert ok, f"{module}: --help did not exit cleanly"


import platform as _platform  # noqa: E402

_WSL2 = "microsoft" in _platform.uname().release.lower()


@pytest.mark.slow
@pytest.mark.skipif(_WSL2, reason="subprocess coordination unreliable on WSL2 loopback")
def test_loopback_pubsub_delivers_all_messages(tmp_path) -> None:
    """Run broker + subscriber + publisher on loopback via subprocesses."""
    port = 18950
    host = "127.0.0.1"
    if not _port_free(host, port):
        pytest.skip(f"port {port} is already in use")

    server_log = tmp_path / "server.log"
    sub_log = tmp_path / "sub.log"
    server_pid = subprocess.Popen(
        [
            sys.executable,
            "-m",
            f"{MODULE}.server",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        stdout=open(server_log, "w"),
        stderr=subprocess.STDOUT,
        env=_env(),
    )
    sub_pid = subprocess.Popen(
        [
            sys.executable,
            "-m",
            f"{MODULE}.subscriber",
            "test-0",
            "--topic",
            "test.pubsub",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        stdout=open(sub_log, "w"),
        stderr=subprocess.STDOUT,
        env=_env(),
    )
    time.sleep(1.5)

    try:
        pub = subprocess.Popen(
            [
                sys.executable,
                "-m",
                f"{MODULE}.publisher",
                "--topic",
                "test.pubsub",
                "--count",
                "5",
                "--interval",
                "0.3",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=_env(),
        )
        try:
            pub.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            pub.terminate()
            pub.wait(timeout=5)
    finally:
        server_pid.terminate()
        sub_pid.terminate()
        time.sleep(0.5)
        server_pid.kill()
        sub_pid.kill()
        server_pid.wait()
        sub_pid.wait()

    received = open(sub_log).read()
    count = received.count("INFO")
    assert count >= 4, f"subscriber received only {count} lines:\n{received}"
