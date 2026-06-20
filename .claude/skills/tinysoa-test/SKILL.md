---
name: tinysoa-test
description: Test engineer for tinySOA (SOA framework) — designs test strategy and generates pytest tests (incl. @pytest.mark.asyncio), ABC contract tests, ServiceStatus FSM tests, policy tests (retry/timeout/circuit-breaker), and EventBus implementation tests. Runs via PYTHONPATH=src pytest + uv. someip is one protocol stack; SomeIPEventBus tests mock pysomeip or run on loopback.
---

# tinysoa-test: Test Engineer

You are a tinySOA test engineer. Your job is to design test strategies, generate tests appropriate for this SOA framework, integrate them into the `pytest` workflow, and verify they pass.

## Important: tinySOA Testing Context

tinySOA uses **`pytest` + `pytest-asyncio`** (NOT unittest). Tests live in `tinySOA/tests/`. Run via:

```bash
cd tinySOA
export PYTHONPATH=$PWD/src
# quick (no venv needed):
PYTHONPATH=$PWD/src uvx pytest -q tests
# or with a venv:
uv venv .venv && source .venv/bin/activate && uv pip install -U pytest pytest-asyncio
PYTHONPATH=$PWD/src pytest -q tests
# single file:
PYTHONPATH=$PWD/src pytest tests/test_<module>.py -q
```

Testing characteristics:
- Async tests use `@pytest.mark.asyncio` (the framework is async-first).
- Mocking via `unittest.mock.AsyncMock` / `MagicMock` / `patch`.
- No `conftest.py` / shared fixtures yet — keep tests self-contained or add a `conftest.py` when a fixture is reused ≥3 times.
- SOME/IP stack (`eventbus/someip.py`) depends on pysomeip: `pip install -e .` in the repo root first, then mock the transport or run on loopback with a graceful SKIP if multicast is unavailable.

The test strategy must prefer tests that need **no network** (mock the EventBus/transport). Gate real-socket tests (TCP/SomeIP) behind loopback checks and SKIP gracefully.

## When Invoked

1. **Standalone** (`/tinysoa-test`): Generate tests for all changed files.
2. **Sub-skill**: Called by `tinysoa-dev` or `tinysoa-pr` with specific changes that need tests.

## Phase 1: Analyze Test Scope

### Collect Context

```bash
# Identify changed files
git diff --name-only HEAD -- 'tinySOA/**/*.py'
# Existing tests
ls tinySOA/tests/
# Confirm framework
grep -nE 'pytest|@pytest.mark.asyncio|AsyncMock' tinySOA/tests/*.py | head
```

### Component Mapping (what to test for each subpackage)

| Subpackage | Responsibility | Primary test approach |
|---|---|---|
| `core/` | `Service`/`Method`/`Event`/`Endpoint`/`Message`, `ServiceStatus` FSM, error hierarchy | FSM transition tests, validation, error types |
| `api/` | ABCs: `ServiceRegistry`, `ServiceInvoker`, `EventPublisher`, `EventSubscriber` | Contract tests: every impl satisfies the ABC |
| `eventbus/` | `EventBus` ABC + `InMemory`/`TCP`/`SomeIP` impls, `EventMessage`, topic matching | Contract tests + impl behaviour (mock/loopback) |
| `runtime/` | `Container`, `LifecycleManager` | Add/remove/start/stop lifecycle |
| `spi/` | `Interceptor`, `InterceptorChain`, `InvocationContext`, `Plugin` | Chain ordering by priority, before/after hooks |
| `policies/` | `RetryPolicy`, `TimeoutPolicy`, `CircuitBreaker` | Policy behaviour with `AsyncMock` (backoff, jitter, open/half-open) |
| `obs/` | `MetricsCollector`/exporters, `TracingInterceptor` | Counter/gauge/histogram, trace context propagation |
| `config/` | `ConfigLoader`, `Config` schema | Multi-source load + merge precedence |
| `examples/` | echo/pubsub/someip demos | Smoke import + arg parse; optional loopback run |

### Determine Test Type

| Change Type | Test Strategy | Test Method |
|---|---|---|
| New ABC / interface | Contract test | Verify every concrete impl satisfies the ABC |
| New `EventBus` impl | Contract + behaviour | All 4 abstract methods + pub/sub semantics |
| `ServiceStatus` change | FSM test | Every legal transition ok; illegal → `StateError` |
| New policy | Behaviour test | `AsyncMock` raising/latency; backoff/jitter; breaker states |
| New interceptor | Chain test | Priority ordering; error propagation; context fields |
| Config change | Merge test | file/env/dict precedence; validation |
| Bug fix | Regression test | Minimal failing case, assert fixed |

### Identify Test Dependencies

```bash
# Does the change touch real sockets / multicast / TCP?
grep -nE 'create_datagram_endpoint|create_connection|multicast|socket\.' tinySOA/src/tinysoa/eventbus/<file>.py
# Does it depend on pysomeip?
grep -nE 'from someip|import someip' tinySOA/src/tinysoa/**/*.py
# Async / timing?
grep -nE 'async def|await |asyncio\.|sleep\(' tinySOA/src/tinysoa/<file>.py
```

## Phase 2: Generate Tests

### Strategy A: ABC Contract Tests (api/, eventbus/)

For every ABC, assert concrete implementations satisfy the contract. This is the highest-value test class for an interface-first framework.

```python
from __future__ import annotations

import inspect
import pytest

from tinysoa.eventbus.bus import EventBus
from tinysoa.eventbus import InMemoryEventBus


def test_inmemory_bus_implements_eventbus_contract() -> None:
    bus = InMemoryEventBus()
    # All abstract methods are implemented (instantiation already proves it)
    assert isinstance(bus, EventBus)
    for name in ("publish", "subscribe", "unsubscribe", "get_subscribers_count"):
        assert callable(getattr(bus, name)), f"missing {name}"


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber() -> None:
    from tinysoa.eventbus.message import EventMessage
    bus = InMemoryEventBus()
    received: list = []
    sub = bus.subscribe("topic.a", lambda msg: received.append(msg))  # adjust handler shape to API
    await bus.publish(EventMessage(topic="topic.a", payload=b"x"))
    assert len(received) == 1
    bus.unsubscribe(sub)
```

### Strategy B: ServiceStatus FSM Tests (core/)

```python
from __future__ import annotations

import pytest

from tinysoa.core.model import Service, ServiceStatus
from tinysoa.core.errors import StateError


def test_legal_transitions() -> None:
    s = Service(...)  # fill required fields
    s.register();  assert s.status == ServiceStatus.REGISTERED
    s.start();     assert s.status == ServiceStatus.RUNNING
    s.stop();      assert s.status == ServiceStatus.STOPPED
    s.start();     assert s.status == ServiceStatus.RUNNING   # STOPPED->RUNNING allowed


def test_illegal_transition_raises_state_error() -> None:
    s = Service(...)                       # status == INIT
    with pytest.raises(StateError):
        s.stop()                           # INIT -> STOPPED is illegal
```

### Strategy C: Policy Tests (policies/)

```python
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock

from tinysoa.policies.retry import RetryPolicy


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures() -> None:
    func = AsyncMock(side_effect=[RuntimeError, RuntimeError, "ok"])
    policy = RetryPolicy(max_attempts=3)
    result = await policy(func)
    assert result == "ok"
    assert func.await_count == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_reraises() -> None:
    func = AsyncMock(side_effect=RuntimeError("nope"))
    policy = RetryPolicy(max_attempts=3)
    with pytest.raises(RuntimeError):
        await policy(func)
    assert func.await_count == 3
```

### Strategy D: EventBus Implementation Tests (eventbus/)

- **InMemory**: pure-Python, no network — fastest, cover pub/sub, topic matching, unsubscribe, metrics.
- **TCP**: loopback server+client in one process via `asyncio`; SKIP if port unavailable.
- **SomeIP**: mock `someip.sd`/`someip.service` with `AsyncMock`/`patch` to assert topic↔eventgroup mapping and lifecycle; OR run on loopback multicast with SKIP guard.

```python
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_someip_bus_maps_topic_to_eventgroup(monkeypatch) -> None:
    # Mock pysomeip transport so no real sockets are opened
    ...  # patch ServiceDiscoveryProtocol/SimpleService; assert mapping is bidirectional & consistent
```

For real-socket tests, ALWAYS:
- `@pytest.mark.asyncio` + `asyncio.wait_for(...)` with a generous timeout to avoid CI hangs.
- `try/finally` (or an async fixture) to close transports and cancel tasks — no `Task was destroyed but it is pending!`.
- SKIP gracefully when multicast/ports unavailable.

### Strategy E: Interceptor Chain Tests (spi/)

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from tinysoa.spi.interceptor import InterceptorChain, InvocationContext


@pytest.mark.asyncio
async def test_interceptors_run_in_priority_order() -> None:
    order: list[str] = []
    # add two interceptors with different priority; assert order list matches ascending priority
    ...
```

### Test Generation Rules

For every behaviour being tested, generate AT LEAST:
1. **One happy path** — normal input, expected output.
2. **One error path per failure mode** — each framework exception branch.
3. **Edge cases** — empty topic, duplicate subscribe, unsubscribe-then-publish, full FSM cycle.
4. **Contract compliance** — for any new ABC implementation.
5. **Async lifecycle** — for coroutines: cancellation + resource cleanup.

### Test Anti-Patterns to Avoid

- Do NOT use `unittest.TestCase`/`pytest`-incompatible fixtures — this is a pytest project.
- Do NOT omit `@pytest.mark.asyncio` on async tests (they won't run).
- Do NOT leave background asyncio tasks running — cancel and await in teardown.
- Do NOT use `time.sleep` in async tests — use `await asyncio.sleep`.
- Do NOT open real SOME/IP multicast without a SKIP guard.
- Do NOT duplicate pysomeip logic in tests — mock it.

## Phase 3: Integrate with Build System

tinySOA runs from source via `PYTHONPATH=src` (no installed package yet). Integration is light:
- New tests go in `tinySOA/tests/test_<area>.py` (pytest auto-discovers `test_*`).
- If a fixture is reused across ≥3 tests, promote it to a `tinySOA/tests/conftest.py`.
- Keep `pytest-asyncio` mode consistent (asyncio_mode = auto OR explicit markers — match the existing style).

```bash
# Verify discovery picks up the new file
cd tinySOA && PYTHONPATH=$PWD/src pytest tests/test_<area>.py -q --collect-only | head
```

## Phase 4: Run and Verify

```bash
cd tinySOA
export PYTHONPATH=$PWD/src
pytest -q tests                                   # full suite
pytest tests/test_<area>.py -q                    # focused
ruff check src/ tests/ 2>/dev/null || true        # if ruff available
mypy --show-error-codes src/ 2>/dev/null || true  # if mypy available
```

### If Tests Fail

1. Read the pytest traceback carefully.
2. Decide if the test is wrong or the code is wrong.
3. If the test is wrong: fix the test.
4. If the code is wrong: report to the calling skill (`tinysoa-dev` / `tinysoa-pr`).
5. Re-run until green.

## Phase 5: Coverage Report

```
## Test Report

### Test Files Generated / Modified
- tests/test_<area>.py — N test cases

### Test Strategy
| Test Type | Count | Coverage Target | Network Required |
|-----------|-------|-----------------|------------------|
| ABC contract | N | impl satisfies ABC | No |
| ServiceStatus FSM | N | legal/illegal transitions | No |
| Policy behaviour | N | retry/timeout/breaker | No |
| Interceptor chain | N | priority ordering | No |
| EventBus impl | N | pub/sub + matching | Mock/loopback |
| Config merge | N | file/env/dict precedence | No |

### Execution Results
| Suite | Result | Notes |
|-------|--------|-------|
| pytest tests | PASS | N tests |
| ruff (if avail) | clean | |
| mypy (if avail) | clean | |

### Coverage Assessment
- New behaviour tested: yes/no
- Error paths covered: N / M
- Untested (and why): [list]
```

## EVOLUTION_REPORT

```
EVOLUTION_REPORT {
  skill: "tinysoa-test"
  task_summary: "Test generation for <area>"
  tests_generated: N
  tests_passed: N
  tests_failed: N
  tests_skipped: N
  contract_tests: N
  async_tests: N
  error_paths_covered: N
  edge_cases_covered: N
  network_required: true/false
  component: "..."
}
```
