# tinySOA Test Optimization Framework

> Status: proposal — implement incrementally as the suite grows.

## 1. Current State (layered structure, 2026-06-20)

**131 tests passing, 4 skipped, 0 failures** — 47s on local loopback.

### Test Organization

```
tests/
├── conftest.py                     # shared fixtures
├── unit/         (8 files)         # fast, no network, always-run gate
├── integration/  (5 files)         # multi-component, may use loopback
├── examples/     (5 files)         # example verification (import/wiring)
└── system/       (12 ST dirs)      # standalone scripts, SKIP-guarded
```

### Coverage by Subpackage

| Subpackage | Layer | Files |
|---|---|---|
| `core/` | unit | test_core_model, test_runtime_lifecycle |
| `api/` | unit | test_api_contracts |
| `policies/` | unit | test_policies |
| `spi/` | unit | test_interceptors_plugins |
| `obs/` | unit | test_observability |
| `config/` | unit | test_config_merge, test_config_system |
| `eventbus/` (InMemory+TCP) | integration | test_event_bus |
| `eventbus/` (SomeIP) | integration | test_someip_bus, test_service_discovery_proto, test_cross_process_someip |
| examples (all 6) | examples | test_example_echo, _interceptor_auth, _pubsub_multi, _multi_publishers, _someip_multi |
| system | system/ST-* | standalone scripts (not pytest) |

**Resolved tech debt**:
- ✅ `pyproject.toml` created — `asyncio_mode = "auto"`, markers registered.
- ✅ Shared fixtures in `tests/conftest.py` (`event_bus`, `event_message`, `free_port`).
- ✅ Stale path logic fixed in all 5 Makefiles, 3 tmux_demo.sh, 3 Python files, eventbus/__init__.py.
- ✅ `tests/system_tests` renamed to `tests/system`.
- ✅ Example duplication removed (`src/tinysoa/examples/` deleted).

**Remaining**:
- `test_someip_bus_extended.py` is an empty stub ("implementation deferred").
- Cross-process SOME/IP delivery intermittently fails on WSL2 loopback (pysomeip SD race) → skip-guarded.

## 2. Recommended pytest Configuration

Add a minimal `pyproject.toml` at the repo root:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = ["-ra", "--strict-markers", "--color=yes"]
markers = [
    "unit: fast, no network, no side-effects (default CI)",
    "integration: multi-component, may use loopback but no external processes",
    "slow: >5 s or spawns real subprocesses",
    "network: opens real sockets (TCP / SOME/IP); needs clean loopback",
    "someip_loopback: SOME/IP SD + unicast on loopback; requires pysomeip + clean SD",
]
filterwarnings = [
    "error",
    # asyncio teardown noise from pysomeip SD layer (benign)
    "ignore::RuntimeWarning:.*_start_subscription.*",
]
```

**Transition**: once `asyncio_mode = "auto"` is set, the explicit `@pytest.mark.asyncio` markers become optional (pytest-asyncio auto-detects async test functions). The explicit markers can be removed over time; they are harmless if left.

## 3. Marker Taxonomy

| Marker | Purpose | Run profile |
|---|---|---|
| `unit` | Import/wiring/fsm/policy — pure, fast (<1 s), no IO | `-m unit` (default CI gate) |
| `integration` | Multi-component in-process (eventbus loopback, interceptor chain) | `-m "unit or integration"` |
| `slow` | Real subprocesses, >5 s | `-m slow` (nightly / pre-merge) |
| `network` | Real sockets (TCP / SOME/IP) | `-m network` (host-dependent) |
| `someip_loopback` | SOME/IP SD + unicast on loopback | requires clean SD env |

**Recommended gate commands:**
```bash
pytest -m "not slow and not network"          # fast-only (CI push)
pytest -m "not network"                       # unit+integration (CI PR)
pytest --run-slow                             # full local (needs conftest opt-in)
```

## 4. Shared Fixtures (`tests/conftest.py` / `tests/examples/conftest.py`)

### Core fixtures (add to existing `tests/conftest.py`)

```python
import pytest
import socket
from tinysoa.eventbus import InMemoryEventBus
from tinysoa.eventbus.message import EventMessage


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    """A fresh InMemoryEventBus for each test (no network, no teardown)."""
    return InMemoryEventBus()


@pytest.fixture
def event_message() -> EventMessage:
    """Canonical test message."""
    return EventMessage(topic="test.topic", payload={"hello": "world"})


@pytest.fixture
def free_port() -> int:
    """Return an OS-assigned free TCP port (binds then releases)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]
```

### Example-specific fixtures (`tests/examples/conftest.py`)

```python
import sys
from pathlib import Path
import pytest

# Path helpers shared by all example tests.
_CLAUDE_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def example_pythonpath() -> dict[str, str]:
    """Subprocess env carrying PYTHONPATH for examples (session-scoped)."""
    import os
    return {
        **os.environ,
        "PYTHONPATH": ":".join(
            str(_CLAUDE_ROOT / d)
            for d in ("src", "third_party/pysomeip/src")
        ),
    }


@pytest.fixture(scope="session")
def someip_example_dir() -> str:
    """Return the absolute path of ``examples/someip_multi_publishers``."""
    return str(_CLAUDE_ROOT / "examples" / "someip_multi_publishers")
```

## 5. Contract-Test Parametrization

Replace per-impl duplication with a single parametrized test:

```python
from tinysoa.eventbus.bus import EventBus
from tinysoa.eventbus import InMemoryEventBus

CONCRETE_BUSES = [
    InMemoryEventBus,
]
try:
    from tinysoa.eventbus.someip import SomeIPEventBus
    CONCRETE_BUSES.append(SomeIPEventBus)
except ImportError:
    pass


@pytest.mark.parametrize("bus_cls", CONCRETE_BUSES)
def test_every_bus_implements_eventbus_contract(bus_cls, monkeypatch):
    """All concrete EventBus implementations satisfy the ABC."""
    if bus_cls is SomeIPEventBus:
        from unittest.mock import AsyncMock
        monkeypatch.setattr("someip.service.SimpleService.create_unicast_endpoint", AsyncMock())
        monkeypatch.setattr("someip.sd.ServiceDiscoveryProtocol.create_unicast_endpoint", AsyncMock())
    bus = bus_cls(...)  # minimal init
    assert isinstance(bus, EventBus)
```

This replaces separate tests for each impl and makes adding a new EventBus (e.g., ZeroMQ) a one-line change.

## 6. Network Gating Strategy

Every test that touches real sockets MUST use one of these patterns:

### Pattern A: Port-probe skip (single-port)
```python
@pytest.mark.network
def test_tcp_echo(free_port):
    if not _port_free("127.0.0.1", free_port):
        pytest.skip(f"port {free_port} in use")
```

### Pattern B: SD-availability skip (SOME/IP)
```python
@pytest.mark.someip_loopback
def test_someip_delivery():
    """Full delivery test.  Only runs when SD handshake is reliable."""
    # Probe: try a quick SOMIP subscription handshake
    if _sd_handshake_fails(reason):
        pytest.skip(f"SD handshake unreliable: {reason}")
```

### Pattern C: Skip-gate fixture (reusable)
```python
@pytest.fixture
def skip_if_sd_contended():
    """Skip the calling test if SD multicast is not usable."""
    import subprocess, sys
    probe = subprocess.run(
        [sys.executable, "-c",
         "from someip.sd import ServiceDiscoveryProtocol; ..."],
        capture_output=True, text=True, timeout=5,
    )
    if "NACK" in (probe.stdout + probe.stderr):
        pytest.skip("SD multicast contends")
```

### Current skip status (WSL2 loopback, 2026-06-20)

| Test | Reason | Needs |
|---|---|---|
| `test_cross_process_someip` | pysomeip SD delivery race on WSL2 | clean Linux loopback |
| `test_loopback_pubsub` | Port contention in full-suite ordering | exclusive port + sequential run |
| `test_someip_sensor_delivery` | SD delivery race (same as above) | clean Linux loopback |

On Linux with clean loopback, all three skip-gates should pass.

## 7. Stub Cleanup

`tests/test_someip_bus_extended.py` (105 lines, 0 tests collected):

```
@pytest.mark.skip(reason="Design-only scope: test implementation deferred")
```

Either **implement** the deferred tests (RPC method invocation, interceptor chains, load-balancing patterns — the file already has the test-class scaffold) or **remove** the file to avoid confusion. Recommend: implement in next SOME/IP feature cycle.

## 8. CI Shape (proposal)

```yaml
# .github/workflows/test.yml
test-fast:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with: { submodules: recursive }
    - uses: astral-sh/setup-uv@v5
    - run: uv venv .venv && uv pip install pytest pytest-asyncio
    - run: .venv/bin/python -m pytest tests/ -m "not slow and not network" -q

test-full:
  runs-on: ubuntu-latest
  if: github.event_name == 'pull_request'
  steps:
    - uses: actions/checkout@v4
      with: { submodules: recursive }
    - uses: astral-sh/setup-uv@v5
    - run: uv venv .venv && uv pip install pytest pytest-asyncio
    - run: .venv/bin/python -m pytest tests/ -q
```

Fast gate (`-m "not slow and not network"`) on every push (3.7 s locally); full suite on PR (47 s locally; slower in CI due to subprocess spawning).

## 9. Regression Principles

### Core Principle

**Any test that previously passed MUST continue to pass.** A `SKIP` is acceptable only when the environment is known-unavailable. A `FAIL` is NEVER acceptable on `main`.

### Regression Gates

| Gate | Trigger | Command | Blocking? |
|---|---|---|---|
| `unit` | every commit / push | `pytest tests/unit -q` | ✅ blocking |
| `unit+integration` | every PR | `pytest tests/unit tests/integration -q -m "not slow"` | ✅ blocking |
| `unit+integration+examples` | pre-merge | `pytest tests/unit tests/integration tests/examples -q` | ✅ blocking |
| `system` | on-demand, clean loopback | `python tests/system/ST-*/run_test.py` (standalone) | advisory |

### Change → Regression Flow

1. Branch from `main`
2. Make changes + add/update tests
3. Gate 1: `pytest tests/unit -q` → **MUST pass** (fast, < 2 s)
4. Gate 2: `pytest tests/unit tests/integration -q -m "not slow"` → **MUST pass** (< 10 s)
5. Gate 3: `pytest tests/unit tests/integration tests/examples -q` → **MUST pass** (< 10 s)
6. Full: `pytest tests/ -q` → all PASS or SKIP (no FAIL)
7. Merge only when all gates are green

### Layer Semantics

| Layer | What goes here | Network? | Subprocess? | Max runtime |
|---|---|---|---|---|
| `tests/unit/` | FSM, policy, interceptor, config, ABC contract, observability | No | No | 2 s |
| `tests/integration/` | EventBus impls, SD protocol, cross-process wiring | Mock / loopback | Yes (cross_process) | 45 s (with slow) |
| `tests/examples/` | Example import-smoke, wiring consistency, arg-parsing | No (fast) / Yes (loopback template) | Yes (pubsub loopback) | 3 s |
| `tests/system/` | Standalone scripts (ST-*). NOT collected by pytest | Yes (SOME/IP) | Yes (multi-process) | N/A |

### Skip vs Fail

- **FAIL**: A genuine code or test defect. Must be fixed before merge.
- **SKIP**: Environment is known-unavailable (WSL2 SD race, port in use, CI runner without multicast). Must include a `reason=` string explaining *what* is unavailable.

A test that *always* skips on a given host is acceptable only if documented in the skip reason. Tests must pass in CI (Linux, clean loopback).

## 10. Implementation Priority

| # | Item | Effort | Impact |
|---|---|---|---|
| 1 | `pyproject.toml` with markers + asyncio_mode | 5 min | silences warnings, enables auto-asyncio |
| 2 | Remove stale `sys.path` hacks in test files (conftest handles it) | 15 min | dedups ~10 files |
| 3 | Add shared fixtures to `tests/conftest.py` | 10 min | reduces boilerplate in new tests |
| 4 | Parametrize EventBus contract tests | 10 min | DRY |
| 5 | Implement `test_someip_bus_extended` or delete | 30 min / 1 min | resolve stub |
| 6 | CI workflow | 10 min | automated gating |
| 7 | `tests/examples/conftest.py` with example-specific fixtures | 10 min | new example tests DRY from the start |
