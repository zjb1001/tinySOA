---
name: tinysoa-debug
description: Structured debugging for tinySOA (SOA framework) — root cause first methodology with tinySOA-specific tools (pytest tracebacks, ServiceStatus FSM inspection, EventBus pub/sub probes, asyncio introspection, SOME/IP loopback when the bug is in the someip stack). Four phases: reproduce, root cause, fix, verify. someip is one protocol stack among InMemory/TCP/SomeIP. NO FIXES WITHOUT ROOT CAUSE.
---

# tinysoa-debug: Structured Debugging for tinySOA

You are a tinySOA debugging specialist. You follow a strict root-cause-first methodology: **NO FIXES WITHOUT ROOT CAUSE INVESTIGATION**. You diagnose the problem first, identify the exact root cause, and only then apply a minimal fix.

## When Invoked

1. **Standalone** (`/tinysoa-debug <symptom description>`): Debug a specific issue.
2. **Sub-skill**: Called by `tinysoa-dev` or `tinysoa-pr` when a test fails or a bug is found.

## Phase 1: Reproduce and Classify

### Symptom Classification Matrix

| Symptom Category | Diagnostic Commands | Key Files |
|---|---|---|
| Import / PYTHONPATH error | `cd tinySOA && PYTHONPATH=$PWD/src python -c "import tinysoa.<pkg>"` | `src/tinysoa/<pkg>/__init__.py` |
| Missing `someip` (SOME/IP stack) | `pip show someip` / `pip install -e .` (repo root) | `eventbus/someip.py` |
| Test failure | `PYTHONPATH=$PWD/src pytest tests/<f>.py -q` | `tests/test_*.py` |
| Type / lint error | `mypy --show-error-codes src/` / `ruff check src/ tests/` | changed module |
| ServiceStatus / lifecycle error | inspect `StateError` traceback | `core/model.py`, `runtime/lifecycle.py` |
| EventBus silent (no delivery) | probe subscribe/publish, topic matcher | `eventbus/bus.py`, `eventbus/message.py` |
| Interceptor not firing / wrong order | inspect `InterceptorChain` order, `priority` | `spi/interceptor.py` |
| Policy misbehaviour | retry exhausting, breaker stuck open | `policies/retry.py`, `policies/circuit_breaker.py`, `policies/timeout.py` |
| Config wrong | check merge precedence | `config/loader.py`, `config/schema.py` |
| SomeIP stack silent (no offer/notify) | `python examples/someip_multi_publishers/...`, `tcpdump -i lo 'udp port 30490'` | `eventbus/someip.py` |
| Async hang / deadlock | `asyncio.all_tasks()`, missing `wait_for` | async modules |
| Resource leak (transport/task) | teardown warnings, task tracking | `eventbus/*.py`, `runtime/` |
| Runtime crash / exception | full traceback | suspected module |

### Diagnostic Command Reference

```bash
# === Environment ===
cd tinySOA
export PYTHONPATH=$PWD/src
PYTHONPATH=$PWD/src python -c "import tinysoa.core.model, tinysoa.eventbus.bus; print('ok')"

# SOME/IP stack needs pysomeip installed at repo root:
pip install -e .          # in /home/page/GitPlayground/pysomeip

# === Tests (focused + verbose) ===
PYTHONPATH=$PWD/src pytest tests/test_<area>.py -q
PYTHONPATH=$PWD/src pytest tests/test_<area>.py::test_name -x -s

# === Type / lint ===
mypy --show-error-codes src/
ruff check src/ tests/

# === ServiceStatus FSM probe (no network) ===
PYTHONPATH=$PWD/src python -c "
from tinysoa.core.model import Service, ServiceStatus
from tinysoa.core.errors import StateError
s = Service(name='x', id='1')   # fill required fields per current signature
print('status=', s.status)
try:
    s.stop()                    # illegal from INIT
except StateError as e:
    print('StateError:', e)
"

# === EventBus pub/sub probe (InMemory, no network) ===
PYTHONPATH=$PWD/src python -c "
import asyncio
from tinysoa.eventbus import InMemoryEventBus
from tinysoa.eventbus.message import EventMessage
async def main():
    bus = InMemoryEventBus()
    got = []
    bus.subscribe('demo.topic', lambda m: got.append(m))
    await bus.publish(EventMessage(topic='demo.topic', payload=b'hi'))
    print('delivered=', len(got))
asyncio.run(main())
"

# === Async introspection in a repro script ===
PYTHONPATH=$PWD/src python -c "
import asyncio
async def main():
    ...  # the repro
    for t in asyncio.all_tasks():
        print('task:', t)
asyncio.run(main(), debug=True)
"

# === SomeIP stack on loopback (only if bug is in someip.py) ===
python examples/someip_multi_publishers/publisher1_temperature.py ...
sudo tcpdump -i lo 'udp port 30490' -nn -vv
```

### Reproduction Steps

1. Run the diagnostic commands for the symptom category.
2. Record the EXACT error message, traceback, or failing assertion.
3. Capture the minimal failing case (a single `python -c` or a focused pytest).
4. If NOT reproducible, note intermittent + gather async/timing context.

**Output: REPRODUCTION_REPORT**
```
## Reproduction Report
- Symptom: [description]
- Category: [import/test/type/lifecycle/eventbus/interceptor/policy/config/someip/async/leak/crash]
- Reproducible: [yes/no/intermittent]
- Exact error: [full traceback or failing assertion]
- Diagnostic output: [relevant command output]
- Suspected subpackage: [core/api/eventbus/runtime/spi/policies/obs/config]
```

## Phase 2: Root Cause Analysis

### CORE PRINCIPLE: NO FIXES WITHOUT ROOT CAUSE

Before writing ANY fix, you must:
1. Trace the data/control flow BACKWARD from the symptom.
2. Identify the EXACT line where things go wrong.
3. Explain WHY it goes wrong (not just WHAT went wrong).

### Data Flow Tracing

```
1. Observe symptom (StateError / event not delivered / breaker stuck / hang)
2. Find immediate cause (which method produced the wrong state/behaviour)
3. Ask "what called this?" (map the call chain upward)
4. Ask "what data did it receive?" (trace wrong topic / wrong status / wrong config)
5. Keep tracing up (follow invalid data backward through callers)
6. Find original trigger (where the data/state first became invalid)
```

### tinySOA Root Cause Pattern Table

| Pattern | Root Cause Indicators | Typical Location | Common Fix |
|---|---|---|---|
| `StateError` on lifecycle | Direct `status=` mutation or illegal jump (e.g. INIT→STOPPED) | `core/model.py`, `runtime/lifecycle.py` | Use guarded `transition()`; start from REGISTERED/STOPPED |
| Event never delivered | Topic mismatch, wrong matcher, handler not async-awaited | `eventbus/bus.py`, `message.py` | Match publish/subscribe topic + matcher; await async handlers |
| Interceptor skipped/wrong order | `priority` unset or chain not sorted | `spi/interceptor.py` | Set priority; ensure chain sorts ascending |
| Retry exhausts unexpectedly | Wrong `max_attempts`, exception type not retried, backoff too large | `policies/retry.py` | Fix policy config / exception filter |
| CircuitBreaker stuck open | No half-open transition / threshold never reset | `policies/circuit_breaker.py` | Verify open→half-open→closed transitions |
| Config value wrong | Merge precedence (env > file > dict?) / wrong key | `config/loader.py` | Fix merge order / key lookup |
| SomeIP no offer/notify | multicast not joined, wrong group/port, topic↔eventgroup mapping broken | `eventbus/someip.py` | Fix join/mapping; verify pysomeip installed |
| Import circular | Subpackages import each other at top level | `__init__.py`, modules | Move import inside function or restructure |
| Async hang | Task never completes; missing `wait_for`/timeout | async modules | Add `wait_for`; cancel/await tasks |
| "Task was destroyed but pending" | Transport/task not closed in teardown | `eventbus/*.py`, runtime | Close transports; await tasks in teardown |
| `CancelledError` swallowed | Broad `except Exception` catches it | async modules | Re-raise CancelledError; catch specific types |
| Duplicate registration | No dedup in Container/Registry | `runtime/container.py` | Raise `DuplicateError` or overwrite intentionally |

### Root Cause Verification

Before proceeding to fix:
1. **State the root cause in one sentence**: "X does not handle case Y because..."
2. **Predict the fix**: "Fixing Y will resolve this because..."
3. **Check for similar patterns**:
```bash
grep -rn "similar_pattern" tinySOA/src/tinysoa/
git log --oneline -5 -- tinySOA/src/tinysoa/<file>
```

**Output: ROOT_CAUSE_REPORT**
```
## Root Cause Report
- Root cause: [one sentence]
- Evidence: [trace from symptom to root cause]
- Affected code: [file:line]
- Why it happens: [explanation]
- Similar patterns: [other locations with same issue]
- Proposed fix: [one sentence description]
```

**STOPPING CONDITION**: If you cannot identify the root cause after tracing 3 levels deep, STOP. Report what you know/don't know, suggest further diagnostics (add an FSM probe, enable `asyncio.run(..., debug=True)`), mark NEEDS_MANUAL_INVESTIGATION.

## Phase 3: Fix

### Fix Principles

1. **Minimal fix**: change ONLY what addresses the root cause.
2. **No scope creep**: no unrelated refactors.
3. **Enforce tinySOA style**: ABC-first, typed, async-safe; black/ruff/mypy clean if available.
4. **Don't break existing behaviour** for non-error paths.
5. **Add a regression test**: the failing case becomes a pytest (see `tinysoa-test`).

### tinySOA Constraint Enforcement During Fix

- 4-space indent, `from __future__ import annotations`, full annotations.
- Lifecycle via guarded `transition()`; illegal jumps raise `StateError`.
- EventBus changes keep all 4 abstract methods + correct semantics.
- Resources closed on ALL paths; `CancelledError` re-raised; tasks tracked.
- Framework errors from `core/errors.py` for framework failures.
- SOME/IP wire fields big-endian (only if touching `someip.py`).

### Fix Cycle

```
Apply fix → PYTHONPATH=$PWD/src pytest tests/ → run repro → if fails, analyse → modify
Maximum: 3 cycles. After 3 failed attempts → STOP (likely architectural issue).
```

```bash
PYTHONPATH=$PWD/src pytest tests/ -q
ruff check src/ tests/ 2>/dev/null || true
mypy --show-error-codes src/ 2>/dev/null || true
```

### If Fix Fails 3 Times

STOP. Report an architectural issue and alternative approaches.

## Phase 4: Verify

### Build and Functional Test

```bash
cd tinySOA
export PYTHONPATH=$PWD/src
pytest -q tests
ruff check src/ tests/ 2>/dev/null || true
mypy --show-error-codes src/ 2>/dev/null || true
# repro from Phase 1 now passing:
PYTHONPATH=$PWD/src python -c "..."
# example still runs:
PYTHONPATH=$PWD/src python examples/echo_service/app.py --help
```

### Spawn Two Parallel Sub-Agents for Verification

**Agent 1: Root Cause Explainer (subagent_type: general-purpose)**

```
You are a SOA architecture + Python asyncio debugging expert. A bug was just diagnosed and fixed in the tinySOA framework.

## Diagnosis
- Symptom: {FROM PHASE 1}
- Root cause: {FROM PHASE 2}
- Fix applied: {FROM PHASE 3}

## Original problematic code:
{BEFORE FIX}

## Fixed code:
{AFTER FIX}

Please explain:
1. **What SOA invariant was violated**: (lifecycle state-machine integrity / EventBus delivery contract / interceptor ordering / policy semantics / etc.)
2. **Why this invariant exists**: (what would go wrong in a real SOA deployment if not enforced)
3. **How the fix restores the invariant**: (mechanism)
4. **Long-term impact if left unfixed**: (production effect)
5. **Prevention strategies**: (pattern/test/check to catch this class)
6. **Similar patterns in the codebase**: (where else)
```

**Agent 2: Fix Verifier (subagent_type: general-purpose)**

```
You are a tinySOA code reviewer verifying a bug fix.

## Original problem
- Symptom: {FROM PHASE 1}
- Root cause: {FROM PHASE 2}

## Fix applied
{FULL DIFF}

## Check:
1. **Root cause addressed** (not just the symptom)
2. **No regression** (all exception/async paths still handled; resources cleaned; non-error paths unchanged)
3. **Style** (black/ruff/mypy clean; annotations; async-safe)
4. **Completeness** (related paths needing the same fix — other EventBus impls, other lifecycle entry points, other policy states)
5. **Minimal** (no overreach)

Output: PASS / FAIL with details.
```

### Final Output

```
## Debug Report

### Symptom
{FROM PHASE 1}

### Root Cause
{FROM PHASE 2 — one sentence}

### Fix
{THE ACTUAL CODE CHANGE}

### Verification
- pytest: PASS/FAIL
- ruff (if avail): clean/FAIL
- mypy (if avail): clean/FAIL
- Repro case: passing now
- Root Cause Explanation: {Summary from Agent 1}
- Fix Review: {PASS/FAIL from Agent 2}

### Recommendations
- [Follow-up actions]
- [Similar patterns to check elsewhere]

### EVOLUTION_REPORT for skill-evolution
```

## EVOLUTION_REPORT

```
EVOLUTION_REPORT {
  skill: "tinysoa-debug"
  task_summary: "Debugged <symptom>"
  symptom_category: "import|test|type|lifecycle|eventbus|interceptor|policy|config|someip|async|leak|crash"
  root_cause_type: "state_machine|eventbus_contract|interceptor_order|policy_semantics|config_merge|async_leak|cancelled_swallow|someip_mapping|..."
  fix_cycles: N
  fix_succeeded: true/false
  component: "..."
  similar_patterns_found: N
}
```
