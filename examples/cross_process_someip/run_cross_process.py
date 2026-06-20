"""
Stdlib-only orchestrator: prove cross-process SOME/IP pub/sub.

Spawns the publisher and the subscriber as TWO SEPARATE OS processes (real
subprocesses, not coroutines/threads), wires PYTHONPATH so both `someip`
(pysomeip) and `tinysoa` resolve from source (no install needed), then asserts
that the subscriber process received events the publisher process sent — i.e.
they communicated ONLY through the SOME/IP EventBus (pysomeip SD + unicast
notifications on loopback).

No third-party deps: uses only the Python standard library.

Run from anywhere:

    python tinySOA/examples/cross_process_someip/run_cross_process.py

Exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# --- locate the repo + source roots relative to this file -------------------
# .../tinySOA/examples/cross_process_someip/run_cross_process.py
HERE = Path(__file__).resolve().parent
TINYSOA_DIR = HERE.parents[1]            # .../tinySOA (repo root)
TINYSOA_SRC = TINYSOA_DIR / "src"        # tinysoa package source
# pysomeip is vendored as a git submodule under third_party/.
SOMEIP_SRC = TINYSOA_DIR / "third_party" / "pysomeip" / "src"

# Both packages must be importable from source, no install.
ENV_PYTHONPATH = os.pathsep.join(
    p for p in (str(SOMEIP_SRC), str(TINYSOA_SRC)) if p
)
# `examples.cross_process_someip.*` resolves with cwd = tinySOA dir.
ENV = {**os.environ, "PYTHONPATH": ENV_PYTHONPATH}


def _spawn(module: str, *args: str) -> subprocess.Popen:
    """Spawn a tinySOA example module as its own OS process."""
    return subprocess.Popen(
        [sys.executable, "-m", f"examples.cross_process_someip.{module}", *map(str, args)],
        cwd=str(TINYSOA_DIR),
        env=ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> int:
    want = 3
    # Publish enough events, slowly, for SD to converge and the subscription
    # to stay live while the subscriber collects `want` events.
    publisher = _spawn("publisher", 30, 1.0)
    try:
        # Let the publisher announce its service before the subscriber looks.
        time.sleep(4.0)
        subscriber = _spawn("subscriber", want, 40)
        try:
            sub_out, _ = subscriber.communicate(timeout=60)
            sub_rc = subscriber.returncode
        finally:
            if subscriber.poll() is None:
                subscriber.terminate()
                try:
                    subscriber.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    subscriber.kill()
    finally:
        if publisher.poll() is None:
            publisher.terminate()
            try:
                publisher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                publisher.kill()

    received = [ln for ln in sub_out.splitlines() if "RECEIVED seq=" in ln]
    print("---- subscriber output (tail) ----")
    print("\n".join(sub_out.splitlines()[-12:]))
    print("-----------------------------------")

    ok = sub_rc == 0 and len(received) >= want
    print(
        f"RESULT: subscriber exit={sub_rc}, received={len(received)}/{want} "
        f"=> {'PASS' if ok else 'FAIL'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
