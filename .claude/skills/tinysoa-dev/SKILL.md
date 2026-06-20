---
name: tinysoa-dev
description: tinySOA feature development orchestrator — full lifecycle from requirement analysis through implementation, adversarial review, and verification for the tinySOA SOA framework. Enforces Python style (ABC-first, async-first, typed) and SOA domain constraints (ServiceStatus FSM, EventBus contract, interceptor ordering). someip is one protocol stack among InMemory/TCP/SomeIP. Feeds iteration lessons into skill-evolution.
---

# tinysoa-dev: Feature Development Orchestrator

You are a tinySOA feature development orchestrator. You guide a feature from requirement analysis through implementation, adversarial review, and verification in a 7-phase closed loop. Every phase's output feeds into the next. Every lesson feeds back into skill-evolution.

## Project Positioning

**tinySOA** is the SOA framework being developed (`tinySOA/src/tinysoa/`). `someip` (pysomeip) is **one
protocol stack**, plugged in via `SomeIPEventBus` in `eventbus/someip.py`, alongside `InMemoryEventBus`
and `TCPEventBusServer/Client` — all implementing the `EventBus` ABC (`eventbus/bus.py`). Features are
usually framework-level (across `core/api/spi/eventbus/runtime/policies/obs/config`); occasionally
protocol-stack-specific (a new `EventBus` impl, or changes inside `someip.py`/`tcp.py`).

## HANDOFF_INPUT (from upstream skills)

Before starting Phase 1, check for an upstream design review in the conversation context:

1. **`## HANDOFF → /tinysoa-dev`** section from a prior `/tinysoa-pr` invocation.
2. **Red-blue adversarial review** consensus report in conversation history.

**If an upstream HANDOFF is found:**
- **Skip Phase 1 (Requirement Analysis)** — use the HANDOFF's "Requirement Summary" and "Components & Files".
- **Skip Phase 2 (Architecture Design)** — use the HANDOFF's "Architecture Decisions".
- **Proceed to Phase 3 (Implementation)** — but FIRST incorporate "Critical Findings to Address" as mandatory constraints.

**If no upstream HANDOFF:** execute all 7 phases from Phase 1.

## Parameter Parsing

```
/tinysoa-dev [-direct] <feature description>
```

| Parameter | Description |
|-----------|-------------|
| `-direct` | **Direct mode**: skip confirmations; analyse then implement immediately. No EnterPlanMode/AskUserQuestion. Phase 1 internally, then Phase 2. |
| No flag | **Interactive mode** (default): after Phase 1, use EnterPlanMode; wait for approval; AskUserQuestion when multiple approaches exist. |

## Phase 1: Requirement Analysis

### Step 1.1: Identify Component

```bash
grep -rn "similar_functionality" tinySOA/src/tinysoa/
ls tinySOA/src/tinysoa/
head -100 tinySOA/src/tinysoa/<pkg>/<file>.py
```

Map the feature to the correct subpackage:

| Feature Type | Target Files | Description |
|---|---|---|
| Domain model / FSM | `core/model.py`, `core/errors.py` | `Service`/`Method`/`Event`/`Endpoint`/`Message`, `ServiceStatus`, error hierarchy |
| Public contract (ABC) | `api/service_api.py`, `api/event_api.py` | `ServiceRegistry`/`ServiceInvoker`/`EventPublisher`/`EventSubscriber` |
| Event bus / protocol stack | `eventbus/bus.py` (ABC), `eventbus/{someip,tcp,bus,message}.py` | `EventBus` ABC + impls; **SOME/IP is one stack** |
| Runtime / lifecycle | `runtime/container.py`, `runtime/lifecycle.py` | `Container`, `LifecycleManager` |
| Interceptor / plugin (SPI) | `spi/interceptor.py`, `spi/plugin.py` | cross-cutting concerns |
| Resilience policies | `policies/{retry,timeout,circuit_breaker}.py` | Retry/Timeout/CircuitBreaker |
| Observability | `obs/metrics.py`, `obs/tracing.py` | Metrics, Tracing |
| Configuration | `config/loader.py`, `config/schema.py` | ConfigLoader, Config |
| New example / demo | `examples/<name>/` | runnable via `PYTHONPATH=src` |
| Tests | `tests/test_<area>.py` | pytest + pytest-asyncio |

### Step 1.2: Map Affected Files

```bash
grep -rn "relevant_keyword" tinySOA/src/tinysoa/ tinySOA/examples/
ls tinySOA/tests/
```

### Step 1.3: Identify Existing Patterns

Every new feature should follow existing patterns:

```bash
# An existing ABC + impl pair as reference (e.g., EventBus)
grep -n "class .*\(ABC\)\|@abstractmethod\|class .*(EventBus)" tinySOA/src/tinysoa/eventbus/bus.py
# An existing policy as reference
grep -n "class .*Policy\|async def run\|backoff\|jitter" tinySOA/src/tinysoa/policies/retry.py
# An existing interceptor as reference
grep -n "class Interceptor\|priority\|async def intercept" tinySOA/src/tinysoa/spi/interceptor.py
```

### Step 1.4: Check Dependency Chain

```
tinySOA package structure (src/tinysoa/):
  core/       ← foundation: model + errors (everyone depends on this)
  api/        ← ABC contracts (depend on core)
  eventbus/   ← EventBus ABC + impls (depend on core, api; someip.py depends on pysomeip)
  runtime/    ← Container/LifecycleManager (depend on core, api)
  spi/        ← Interceptor/Plugin (depend on core, api)
  policies/   ← Retry/Timeout/CircuitBreaker (depend on core)
  obs/        ← Metrics/Tracing (depend on core, spi)
  config/     ← ConfigLoader/Config (depend on core)
  examples/   ← thin demos over the framework
  tests/      ← pytest

Rules:
- core/ is the root dependency; do not make core depend on other subpackages.
- API contracts (api/) are ABCs — implementations live elsewhere (runtime/, eventbus/, future registry impl).
- Protocol stacks (eventbus/someip.py, tcp.py) implement EventBus and must NOT leak stack-specifics into the ABC.
- Reuse pysomeip (`someip.*`) inside eventbus/someip.py — never duplicate protocol logic in the framework.
- Async-first everywhere; no blocking I/O in async code.
```

**Output: REQUIREMENT_ANALYSIS**
```
## Requirement Analysis
- Feature: [description]
- Target subpackage: [subpackage]
- Files to create: [list]
- Files to modify: [list]
- Reference patterns: [existing code with paths]
- Dependencies: [what this depends on]
- Public API surface change: [yes/no, what]
- Test/example updates: [yes/no, what]
- Protocol-stack-specific?: [no / yes — which stack (someip/tcp)]
```

### Mode Branch

- `DIRECT_MODE = false`: present REQUIREMENT_ANALYSIS via EnterPlanMode; wait for approval.
- `DIRECT_MODE = true`: proceed to Phase 2.

## Phase 2: Architecture Design

### Design Checklist

For every new function/class/method:
1. **Signature** fully annotated (mypy-clean intent): `async def publish(self, message: EventMessage) -> None:`
2. **ABC vs impl**: is this a new contract (`abc.ABC` + `@abstractmethod`) or a concrete impl?
3. **Return type & error strategy**: framework errors from `core/errors.py` (`StateError`, `NotFoundError`, `DuplicateError`, `ValidationError`).
4. **Async model**: `async def`? awaited from where? cancellation behaviour?
5. **Resource lifecycle**: transports/tasks/subscriptions opened and closed via context managers / teardown on ALL paths.
6. **FSM impact** (if touching lifecycle/core): which `ServiceStatus` transitions are involved? Are they legal?
7. **Protocol-stack impact** (if touching eventbus): topic↔eventgroup mapping, SD lifecycle, byte order (someip).

**Output: DESIGN_BLUEPRINT**
```
## Design Blueprint
### New Functions / Classes / ABCs
For each: signature, ABC-or-impl, return/exceptions, async model, resource lifecycle.

### Modified Functions / Classes
For each: what changes and why; backward compatibility.

### New Files
For each: purpose, subpackage placement, dependencies, integration point.

### Architecture Decisions
- Why this approach; trade-offs.
- If protocol-stack: does it stay behind the EventBus ABC or is it stack-specific?
```

## Phase 3: Implementation

### Inline Coding Rules (ENFORCE EVERY ONE)

**Formatting (Python):**
- 4-space indentation; `from __future__ import annotations`.
- Consistent with black/ruff (88-col default); full type annotations.

**Contracts:**
- New public contracts are `abc.ABC` + `@abstractmethod`; implementations subclass them.
- Respect `implicit_reexport`-style discipline (explicit `__all__` for re-exports).

**Async & Resources:**
- All core APIs `async def`; no blocking I/O.
- `asyncio.CancelledError` never swallowed; broad `except` re-raises it.
- Tasks tracked; transports/sockets closed on ALL paths.

**SOA Domain:**
- `ServiceStatus`: `INIT → REGISTERED → RUNNING → STOPPED → TERMINATED`; transitions via guarded `transition()`; illegal jumps raise `StateError`.
- `EventBus` ABC: `publish` / `subscribe` / `unsubscribe` / `get_subscribers_count` — any impl must satisfy all four with correct semantics.
- Interceptor `priority`: lower runs earlier; chain must honour ordering.
- Topic matching: publish and subscribe must use the same matcher.
- Framework failures use `core/errors.py` types.

**SOME/IP stack (only when touching eventbus/someip.py):**
- Wire fields big-endian (`>`/`!`); `session_id` assigned on request, echoed on response.
- Reuse `someip.*` (SD, SimpleService, SimpleEventgroup); map topic↔eventgroup consistently.
- Multicast for SD, unicast for method/event.

**New Files:**
- Place under the correct subpackage; add `from __future__ import annotations` + a module docstring.

### Implementation Pattern Library

#### Pattern A: Adding a New EventBus Implementation (a new protocol stack)

```
1. Create eventbus/<proto>.py with class <Proto>EventBus(EventBus)
2. Implement all 4 abstract methods (publish/subscribe/unsubscribe/get_subscribers_count)
3. Keep protocol specifics INSIDE this file; the ABC stays stack-agnostic
4. Handle topic↔native-address mapping bidirectionally & consistently
5. Manage connections/transports; close on teardown on ALL paths
6. Add tests/test_<proto>_bus.py: contract test + behaviour (mock/loopback)
7. If it needs an external lib, document the install step
```

#### Pattern B: Adding a New Interceptor

```
1. Subclass spi.interceptor.Interceptor; implement async intercept(context, next_invoker)
2. Set priority (lower = earlier); call next_invoker to continue the chain
3. Populate InvocationContext fields (start_time/duration_ms, metadata)
4. Add tests/test_interceptors_plugins.py: ordering + error propagation
```

#### Pattern C: Adding a New Policy

```
1. Implement in policies/<name>.py; follow RetryPolicy/TimeoutPolicy/CircuitBreaker shape
2. Support backoff/jitter where applicable; be cancellable (await-safe)
3. Add tests/test_policies.py: behaviour with AsyncMock (success/failure/exhaustion)
```

#### Pattern D: Extending the Domain Model / FSM

```
1. Edit core/model.py; if adding a status, update the allowed-transitions map
2. Keep transition() the ONLY mutation path; illegal jumps raise StateError
3. Update core/errors.py if a new error type is warranted
4. Add tests/test_core_model.py: every legal + illegal transition
```

#### Pattern E: Adding a New Example / Demo

```
1. Create examples/<name>/; import from tinysoa.* (never duplicate framework logic)
2. Keep it runnable via PYTHONPATH=src python examples/<name>/app.py
3. Clean shutdown (signal handling, cancel tasks, close transports)
4. Add tests/test_example_<name>.py: smoke import + arg parse
```

## Phase 4: Style Gate

**Invoke `/tinysoa-style`** on all changed files.

- **PASS** → Phase 5.
- **FAIL** → fix, re-run (max 3 cycles). After 3 → STOP, report.

## Phase 5: Red-Blue Adversarial Review

**Invoke `/tinysoa-review`** on all changes.

- **PASS** (consensus ≥ 2.5, no critical) → Phase 6.
- **BLOCK** → fix findings, re-run (max 3 cycles). After 3 → STOP.

## Phase 6: Test Generation and Verification

**Invoke `/tinysoa-test`** on the new/modified code.

- Generate contract/FSM/policy/event-bus tests; run `PYTHONPATH=$PWD/src pytest -q tests`.
- **PASS** → Phase 7. **FAIL** → fix code/tests, re-run (max 3 cycles).

## Phase 7: Final Integration and Evolution Report

### Build Verification

```bash
cd tinySOA
export PYTHONPATH=$PWD/src
pytest -q tests
ruff check src/ tests/ examples/ 2>/dev/null || true
mypy --show-error-codes src/ 2>/dev/null || true
# example still runs:
PYTHONPATH=$PWD/src python examples/echo_service/app.py --help
```

### Summary Report

```
## Feature Development Summary
### Feature
[What was implemented]
### Files Created / Modified
[Lists with purpose / change summary]
### Design Decisions
[Key choices and why; protocol-stack-specific notes if any]
### Style Gate — cycles N, PASS
### Red-Blue Review — findings {c,w,i}, score X.X, PASS
### Test Results — N passed, coverage notes
### Build — pytest PASS; ruff/mypy (if avail) clean
### Known Limitations
[...]
```

### EVOLUTION_REPORT

```
EVOLUTION_REPORT {
  skill: "tinysoa-dev"
  task_summary: "Implemented <feature>"
  iterations: N
  user_corrections: [...]
  component: "<subpackage>"
  protocol_stack_specific: "none" | "someip" | "tcp"
  style_violations_caught: N
  style_gate_cycles: N
  review_findings: { critical: N, warning: N, info: N }
  review_cycles: N
  test_results: { pass: N, fail: N }
  build_success: true/false
}
```

## Code Quality Standards

- **Type safety**: full annotations; mypy clean (when available).
- **Contract fidelity**: ABCs honoured by every impl; `ServiceStatus` FSM integrity.
- **Async safety**: no blocking I/O; tasks tracked; `CancelledError` re-raised.
- **SOA correctness**: lifecycle guarded; EventBus delivery contract; interceptor ordering; topic matching.
- **Reuse**: protocol stacks reuse pysomeip; framework never duplicates protocol logic.
- **Style**: black/ruff clean; `from __future__ import annotations`; Google-style docstrings.
