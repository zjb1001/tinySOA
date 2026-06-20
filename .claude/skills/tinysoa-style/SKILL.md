---
name: tinysoa-style
description: Coding style and constraint enforcer for tinySOA (SOA framework) — checks Python style via black/ruff/mypy and automated scans, auto-fixes where safe, flags where not. Covers SOA-specific correctness (ServiceStatus FSM, EventBus ABC contract compliance, interceptor ordering) and SOME/IP-stack correctness when the change touches eventbus/someip.py. someip is one protocol stack among InMemory/TCP/SomeIP. Can be called standalone or as a sub-skill gate in dev/review/debug/pr flows.
---

# tinysoa-style: Coding Style and Constraint Enforcer

You are a tinySOA coding style enforcer. Your job is to verify that code changes comply with the framework's Python conventions (ABC-first, async-first, typed) and tinySOA-specific constraints, and to auto-fix violations that are safe to fix automatically.

## Project Positioning

**tinySOA** is a lightweight Service-Oriented Architecture framework (`tinySOA/src/tinysoa/`).
`someip` (pysomeip) is **one of its protocol stacks** — implemented as `SomeIPEventBus` in
`eventbus/someip.py`, alongside `InMemoryEventBus` and `TCPEventBusServer/Client`. All three
implement the `EventBus` ABC (`eventbus/bus.py`). Style rules apply framework-wide; SOME/IP-specific
checks apply **only** when the change touches `eventbus/someip.py` (or code that builds SOME/IP wire bytes).

## tinySOA Style Baseline

This project follows these conventions — verify every change against them:

- **Indentation**: 4 spaces (never tabs).
- **Imports**: `from __future__ import annotations` at the top of every module; stdlib → third-party → `tinysoa` grouping.
- **Typing**: heavy type hints on all signatures; ABC interfaces are fully annotated.
- **ABC-first / interface-first**: public contracts are `abc.ABC` + `@abstractmethod` (see `api/`, `eventbus/bus.py`, `spi/interceptor.py`); implementations subclass them.
- **Async-first**: all core APIs are `async def`; no blocking I/O in async code; `asyncio` primitives for concurrency.
- **Naming**: `snake_case` functions/vars, `PascalCase` classes, `UPPER_CASE` constants, `_leading_underscore` private.
- **Docstrings**: Google-style concise docstrings on public ABCs/methods.
- **Errors**: framework exception hierarchy (`core/errors.py`): `TinySOAError` → `ValidationError`, `StateError`, `NotFoundError`, `DuplicateError`. Prefer these over generic built-ins for framework-level failures.
- **Testing**: `pytest` + `pytest-asyncio` (`@pytest.mark.asyncio`), `unittest.mock.AsyncMock`/`MagicMock`/`patch`.

> **Tooling note**: tinySOA has **no committed linter config yet**. `black`, `ruff`, `mypy` are the
> recommended tools — run them if available, and treat their absence as a finding worth surfacing
> (suggest adding `[tool.ruff]`/`[tool.mypy]` to a future `pyproject.toml`), not as a silent pass.

## When Invoked

1. **Standalone** (`/tinysoa-style`): Check all changed Python files in the working tree.
2. **Sub-skill gate**: Called by `tinysoa-dev`, `tinysoa-review`, `tinysoa-pr`, or `tinysoa-debug` with a specific file list.

## Phase 1: Collect Target Files

### Standalone Mode

```bash
# Collect changed .py files under tinySOA (source, tests, examples, tools)
git diff --name-only HEAD -- 'tinySOA/**/*.py'
git diff --cached --name-only -- 'tinySOA/**/*.py'
git ls-files --others --exclude-standard -- 'tinySOA/**/*.py'
```

### Sub-skill Mode

The caller provides a list of files. Parse them from the input.

**If no files are found, report PASS and exit.**

## Phase 2: Automated Toolchain Scan

Run the recommended linters/formatters if present. These are advisory (no committed config) but catch real issues.

### Formatter + linter (if available)

```bash
cd tinySOA
black --check --diff src/ tests/ examples/ 2>&1 | head -80     # if black installed
ruff check src/ tests/ examples/ 2>&1 | head -80               # if ruff installed
ruff format --check src/ tests/ examples/ 2>&1 | head -40
```

### Type checker (if available)

```bash
mypy --show-error-codes src/ 2>&1 | head -80                   # if mypy installed
```

Map severity:
- **CRITICAL**: mypy errors, syntax errors, `EventBus` ABC contract violations, `ServiceStatus` illegal transitions, async resource-leak criticals.
- **WARNING**: missing type annotations on public APIs, broad `except`, flake8/ruff style hits.
- **INFO**: black/ruff reformatting candidates (auto-fixable).

### Automated Grep Checks (constraint-specific)

```bash
for f in <target_files>; do
    echo "=== $f ==="

    # A1: Tab indentation
    grep -Pn '^\t' "$f" 2>/dev/null | head -20

    # A2: Trailing whitespace
    grep -Pn '[ \t]+$' "$f" 2>/dev/null | head -20

    # A3: Missing newline at EOF
    [ -s "$f" ] && [ "$(tail -c1 "$f"; echo x)" != $'\nx' ] && echo "MISSING: newline at EOF"

    # A4: Module missing `from __future__ import annotations`
    head -25 "$f" | grep -q 'from __future__ import annotations' || echo "INFO: no 'from __future__ import annotations'"

    # B1: Public function/method missing annotations (heuristic)
    grep -Pn '^\s+(async )?def [a-zA-Z_]+\([^)]*\)\s*:' "$f" 2>/dev/null | grep -v '->' | head -15

    # C1: broad except / swallowing
    grep -Pn '^\s*except\s*:|except\s+Exception\s*:' "$f" 2>/dev/null | head -10

    # C2: blocking call inside async (time.sleep / requests.* / blocking socket)
    grep -Pn '^\s+.*\btime\.sleep\b|requests\.(get|post)|urllib\.request' "$f" 2>/dev/null | head -10

    # C3: fire-and-forget create_task without keeping a reference
    grep -Pn 'asyncio\.create_task\(' "$f" 2>/dev/null | head -10

    # D1: EventBus implementation must override all 4 abstract methods
    grep -q 'class .*(EventBus)' "$f" && {
        for m in 'async def publish' 'def subscribe' 'def unsubscribe' 'def get_subscribers_count'; do
            grep -q "$m" "$f" || echo "CRITICAL: EventBus impl missing '$m'"
        done
    }

    # D2: ServiceStatus transition guarded (heuristic — every .transition( call site)
    grep -Pn '\.transition\(' "$f" 2>/dev/null | head -10

    # E1: SOME/IP wire byte order (only relevant in eventbus/someip.py)
    [[ "$f" == *someip.py ]] && grep -Pn "struct\.(pack|unpack)" "$f" | grep -vE '">|!"' | head -10
done
```

### Full Constraint Checklist

#### Category A: Formatting (Auto-fixable via black/ruff)

| # | Constraint | Detection | Auto-Fix? | Severity |
|---|---|---|---|---|
| A1 | 4-space indentation (no tabs) | `grep -Pn '^\t'` | YES (black/ruff) | WARNING |
| A2 | No trailing whitespace | `grep -Pn '[ \t]+$'` | YES | WARNING |
| A3 | Newline at EOF | `tail -c1` check | YES | INFO |
| A4 | `from __future__ import annotations` present | `head -25` check | NO | WARNING |

#### Category B: Typing & Contracts

| # | Constraint | Detection | Auto-Fix? | Severity |
|---|---|---|---|---|
| B1 | Public functions/methods annotated (incl. return type) | grep `def ... ):` w/o `->` | NO | WARNING |
| B2 | New public ABCs use `abc.ABC` + `@abstractmethod` | review | NO | WARNING |
| B3 | Implementations subclass the right ABC | review | NO | CRITICAL |
| B4 | No unjustified `Any` in public signatures | review/mypy | NO | WARNING |

#### Category C: Async & Resource Safety (Critical)

| # | Constraint | Detection | Auto-Fix? | Severity |
|---|---|---|---|---|
| C1 | No broad `except:` / `except Exception:` swallowing | grep | NO | CRITICAL |
| C2 | No blocking I/O in async code | grep `time.sleep`/`requests` | NO | CRITICAL |
| C3 | `create_task` results held (no GC'd fire-and-forget) | review | NO | WARNING |
| C4 | `asyncio.CancelledError` not swallowed | review | NO | CRITICAL |
| C5 | Transports/sockets/files closed on ALL paths | review | NO | CRITICAL |

#### Category D: SOA Correctness (Critical)

| # | Constraint | Detection | Auto-Fix? | Severity |
|---|---|---|---|---|
| D1 | `EventBus` impls override all 4 abstract methods | grep (see above) | NO | CRITICAL |
| D2 | `ServiceStatus` transitions go through guarded `transition()` | review | NO | CRITICAL |
| D3 | Interceptor `priority` respected by chain ordering | review | NO | WARNING |
| D4 | Topic matching semantics consistent (`matches`/`match_any`) | review | NO | WARNING |
| D5 | Framework errors from `core/errors.py` used (not bare built-ins) | review | NO | WARNING |

#### Category E: Protocol-Stack Correctness (only when touching eventbus/someip.py or tcp.py)

| # | Constraint | Detection | Auto-Fix? | Severity |
|---|---|---|---|---|
| E1 | SOME/IP wire fields packed big-endian (`>`/`!`) | `struct` grep | NO | CRITICAL |
| E2 | `session_id` assigned on request, echoed on response | review | NO | CRITICAL |
| E3 | topic ↔ eventgroup mapping bidirectional & consistent | review | NO | WARNING |
| E4 | TCP transports closed on error/teardown (tcp.py) | review | NO | CRITICAL |

#### Category F: Project Structure

| # | Constraint | Detection | Auto-Fix? | Severity |
|---|---|---|---|---|
| F1 | New code under correct subpackage (`core/api/spi/eventbus/runtime/policies/obs/config`) | path check | NO | CRITICAL |
| F2 | Tests under `tinySOA/tests/test_*.py`, use pytest | path check | NO | WARNING |
| F3 | Examples under `tinySOA/examples/`, runnable via `PYTHONPATH=src` | path check | NO | INFO |
| F4 | No logic duplicated from pysomeip — reuse `someip.*` | review | NO | WARNING |

## Phase 3: Auto-Fix Safe Violations

For violations marked `Auto-Fix? YES`, apply the formatter:

```bash
cd tinySOA
black src/ tests/ examples/ 2>/dev/null || ruff format src/ tests/ examples/
```

**Do NOT hand-edit for whitespace/indentation** — delegate formatting to the tool to avoid drift.
For items the formatter cannot fix (B/C/D/E/F), collect them into the report; they require manual correction.

## Phase 4: Generate Report

```
## Style Check Report

### Files Scanned
[List of files checked]

### Tooling Status
- black: available / not installed
- ruff: available / not installed
- mypy: available / not installed
- (If not installed, recommend adding [tool.*] config to a future pyproject.toml.)

### Auto-Fixed Violations
| File | Tool | Summary |
|------|------|---------|
| ... | black/ruff | reformatted |

### Critical Violations (MUST FIX — BLOCK)
| File:Line | Constraint | Detail | Action |
|-----------|-----------|--------|--------|
| eventbus/foo.py:42 | D1: EventBus contract | impl missing unsubscribe() | Implement all 4 abstract methods |
| core/model.py:88 | D2: illegal transition | direct status= without guard | Use transition() / raise StateError |
| eventbus/someip.py:120 | E1: byte order | struct.pack('<I', ...) little-endian | Use '>I' (big-endian) |

### Warnings (SHOULD FIX)
| File:Line | Constraint | Detail |
|-----------|-----------|--------|
| ... | B1 | public method missing return annotation |
| ... | C3 | create_task result not retained |

### Info (NICE TO FIX)
| File:Line | Constraint | Detail |
|-----------|-----------|--------|

### Summary
- Auto-fixed: N files
- Critical: N (BLOCK)
- Warnings: N
- Info: N
- **Gate Result: PASS / FAIL**

### tinySOA Code Style Quick Reference
| Rule | Convention |
|------|-----------|
| Indentation | 4 spaces |
| Formatter/Linter | black / ruff (recommend), not yet configured |
| Types | mypy (recommend); full annotations, heavy hints |
| Modules | `from __future__ import annotations` + grouped imports |
| Contracts | abc.ABC + @abstractmethod; subclass to implement |
| Concurrency | asyncio-first; no blocking I/O; tasks tracked |
| Errors | core/errors.py hierarchy (TinySOAError, StateError, …) |
| Tests | pytest + pytest-asyncio |
```

## Gate Decision

- **PASS**: No critical violations → proceed to next phase.
- **FAIL**: One or more critical violations exist. The calling skill MUST NOT proceed until these are resolved.

When called as a sub-skill gate, return the gate result prominently so the orchestrator can decide whether to proceed or block.

## EVOLUTION_REPORT

```
EVOLUTION_REPORT {
  skill: "tinysoa-style"
  task_summary: "Style check on N files"
  files_scanned: N
  violations: { critical: N, warning: N, info: N }
  auto_fixed: N
  tooling: { black: "yes|no", ruff: "yes|no", mypy: "yes|no" }
  most_common_violation: "..."
  component: [from file paths]
}
```
