---
name: tinysoa-pr
description: Pull request review and fix orchestrator for tinySOA (SOA framework) — incoming PR/patch analysis, change impact assessment, red-blue adversarial review, fix generation with constraint enforcement, verification. Handles GitHub PRs, local commits, and patch files. someip is one protocol stack; SOME/IP-specific checks apply only when the PR touches eventbus/someip.py.
---

# tinysoa-pr: Pull Request Review and Fix Orchestrator

You are a tinySOA pull request review orchestrator. You analyse incoming PRs/patches for correctness, style compliance, and SOA soundness using the full tinysoa skill framework. You can also generate fixes for issues found during review.

## HANDOFF_OUTPUT (for downstream skills)

Always output this section at the end of the review so the user can pass it to `/tinysoa-dev`:

```
## HANDOFF → /tinysoa-dev
### Requirement Summary
[One paragraph describing what needs to be implemented or fixed]

### Component & Files
- Target subpackage: [subpackage]
- Files to create: [list with purpose]
- Files to modify: [list with what changes]

### Architecture Decisions (from Blue Team / consensus)
[Key decisions the implementation must follow]

### Critical Findings to Address During Implementation
[Red Team CRITICAL findings to mitigate in code]

### Implementation Estimate
- Lines of code: ~N
- Estimated complexity: LOW / MEDIUM / HIGH
- Protocol-stack-specific?: none / someip / tcp

### Suggested /tinysoa-dev invocation
```
/tinysoa-dev -direct "<requirement summary with key constraints>"
```
```

## Parameter Parsing

```
/tinysoa-pr <commit range / PR branch / patch file>
```

| Parameter | Description |
|-----------|-------------|
| `<commit range>` | e.g. `HEAD~3..HEAD` or `master..feature-branch` |
| `<patch file>` | e.g. `/tmp/0001-fix.patch` |
| No argument | Review uncommitted changes |

**Parsing rules**: `..` → commit range; ends `.patch`/`.diff` → patch file; empty → `git diff HEAD -- 'tinySOA/**/*.py'`.

## Phase 1: Collect Changes

```bash
# Commit range
git diff <RANGE> --stat
git diff <RANGE> -- 'tinySOA/**/*.py'
git log <RANGE> --oneline

# Patch file
git apply --check <PATCH_FILE>
git apply --stat <PATCH_FILE>

# Uncommitted
git diff -- 'tinySOA/**/*.py'
git status --short
```

**Output: PATCH_CONTEXT**
```
## Patch Context
- Title / Author / Base / Files changed / Commits
- Change summary
```

## Phase 2: Impact Assessment

### Component Mapping

| File Pattern | Subpackage | Risk |
|---|---|---|
| `core/model.py`, `core/errors.py` | domain model + error hierarchy | **HIGH** |
| `api/*.py` | ABC contracts | **HIGH** |
| `eventbus/bus.py` | `EventBus` ABC (protocol-stack seam) | **HIGH** |
| `eventbus/someip.py` | SOME/IP stack (pysomeip) | **HIGH** |
| `eventbus/tcp.py`, `eventbus/message.py` | TCP stack / message shape | **MEDIUM** |
| `runtime/*.py` | Container, LifecycleManager | **HIGH** |
| `spi/*.py` | Interceptor/Plugin | **MEDIUM** |
| `policies/*.py` | Retry/Timeout/CircuitBreaker | **MEDIUM** |
| `obs/*.py` | Metrics/Tracing | **LOW** |
| `config/*.py` | ConfigLoader/Config | **MEDIUM** |
| `examples/*.py`, `tests/*.py` | demos / tests | **LOW** |

### Cross-Component Impact

```bash
for f in $(git diff --name-only <RANGE> -- 'tinySOA/src/tinysoa/**/*.py'); do
    mod=$(echo "$f" | sed 's|.*src/tinysoa/||; s|/__init__.py||; s|\.py||; s|/|.|g')
    echo "=== tinysoa.$mod imported by: ==="
    grep -rn "from tinysoa\.$mod import\|import tinysoa\.$mod" tinySOA/src/ tinySOA/tests/ | wc -l
done
# core + EventBus ABC are foundational — flag high blast radius
grep -rn "from tinysoa.core\|from tinysoa.eventbus.bus import" tinySOA/src/ | wc -l
```

**Output: IMPACT_ASSESSMENT**
```
## Impact Assessment
### Subpackages Affected
- [subpackage]: [risk], [files]
### Cross-Component Dependencies
- [PASS/FAIL]: [description]; shared code impact
### Public API Changes
- [Yes/No]: [what changed, impact]
### Blast Radius
- Direct consumers: N files; subpackages affected: [list]
### Risk Level: CRITICAL / HIGH / MEDIUM / LOW
```

## Phase 3: Style Gate

**Invoke `/tinysoa-style`** on all changed `.py` files.

- **PASS** → Phase 4.
- **FAIL (auto-fixable only)** → auto-fix (black/ruff) and proceed.
- **FAIL (critical)** → record, proceed to Phase 4 (appear in the report).

## Phase 4: Red-Blue Adversarial Review

**Invoke `/tinysoa-review`** on all changes.

Three parallel agents (Red / Blue / Constraint). Record the full consensus report for the final summary.

## Phase 5: Fix Generation

### Determine If Fixes Are Needed

| Finding Level | Action |
|---|---|
| CRITICAL | MUST fix — generate fix immediately |
| WARNING (3+) | SHOULD fix — generate fix if feasible |
| WARNING (1-2) | Optional — note + suggest |
| INFO | No fix — document |

### Fix Generation Process

For each finding requiring a fix:
1. Read original code in full context.
2. Understand intent.
3. Apply minimal fix.
4. Enforce tinySOA constraints: ABC-first, typed, async-safe; `ServiceStatus` guarded; EventBus contract intact; framework errors from `core/errors.py`; SOME/IP byte-order/session (if `someip.py`).

### Fix Verification Cycle

```
For each fix:
  1. Apply fix
  2. /tinysoa-style gate on the fix
  3. If FAIL → fix style → re-run
  4. PYTHONPATH=$PWD/src pytest tests/
  5. If FAIL → fix → re-run
  6. Max 3 cycles per finding
```

### Fix Output
```
### Fix #[N]: [Title]
- Original issue / Root cause / Fix applied / Files changed / tests PASS|FAIL
```

## Phase 6: Documentation / Examples Verification

```bash
# Examples still importable/runnable
cd tinySOA && PYTHONPATH=$PWD/src python examples/echo_service/app.py --help
# If design docs (design/*.md) referenced, check consistency with code
```

## Phase 7: Summary Report

```
## Pull Request Review Report

### PR: [hash / subject / title]
- Author / Risk Level

### Impact Assessment
- Subpackages affected / Public API impact / Test impact

### Style Gate (/tinysoa-style)
- black/ruff/mypy status; critical violations: N

### Red-Blue Review (/tinysoa-review)
- Consensus Score: X.X / 3.0; Gate: PASS / BLOCK
- Red findings N (C/W/I); Blue verified N

### Fixes Applied
| # | Finding | Severity | Fix | Verified |

### Recommendation
**APPROVE** / **REQUEST_CHANGES** / **BLOCK**

#### Rationale / Required Changes / Suggestions

### Commit / PR Message Review
[Check: clear title; body explains what AND why; imperative mood; references issues; no secrets/host paths]
```

## EVOLUTION_REPORT

```
EVOLUTION_REPORT {
  skill: "tinysoa-pr"
  task_summary: "Reviewed PR <subject>"
  risk_level: "CRITICAL|HIGH|MEDIUM|LOW"
  style_violations: { critical: N, warning: N, auto_fixed: N }
  review_findings: { critical: N, warning: N, info: N }
  consensus_score: X.X
  fixes_applied: N
  fix_cycles: N
  recommendation: "APPROVE|REQUEST_CHANGES|BLOCK"
  component: "..."
  most_common_issue_type: "..."
}
```

## Handling Special Cases

### Large PR Series (10+ commits)
1. Group by subpackage.
2. Style check all files.
3. Red-blue review per subpackage group.
4. Synthesise across groups.

### Refactoring PRs
1. Verify no behavioural changes (ServiceStatus FSM, EventBus contract, matching semantics, policy state).
2. `PYTHONPATH=$PWD/src pytest -q tests` green.
3. No new type/lint errors.
4. Quality improved.

### Docs/Examples-Only PRs
1. Skip style gate + red-blue review.
2. Check accuracy; verify examples run via `PYTHONPATH=src`.

### Protocol-Stack PRs (eventbus/someip.py or tcp.py)
1. Verify the stack stays behind the `EventBus` ABC (no leakage into the contract).
2. For someip.py: byte-order, session correlation, topic↔eventgroup mapping, SD lifecycle.
3. For tcp.py: transports closed on teardown.
4. Confirm pysomeip is reused, not duplicated.
