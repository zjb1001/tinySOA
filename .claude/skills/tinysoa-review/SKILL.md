---
name: tinysoa-review
description: Red-blue adversarial code review for tinySOA (SOA framework) — Red team attacks code for bugs, SOA correctness issues (ServiceStatus FSM, EventBus ABC contract, interceptor ordering, lifecycle), style violations; Blue team defends correctness. Three-phase process: independent analysis, adversarial debate, consensus. Checks ALL tinySOA-specific constraints. SOME/IP-stack correctness only when the change touches eventbus/someip.py (someip is one protocol stack among InMemory/TCP/SomeIP).
---

# tinysoa-review: Red-Blue Adversarial Code Review

You are orchestrating a red-blue adversarial code review for the tinySOA project. You spawn THREE parallel sub-agents with opposing objectives, then reconcile their findings into a consensus report with a gate decision.

## When Invoked

1. **Standalone** (`/tinysoa-review`): Review uncommitted or recent changes.
2. **Sub-skill**: Called by `tinysoa-dev`, `tinysoa-pr`, or `tinysoa-debug` with specific changes.

## Phase 1: Collect Changes

### Standalone Mode

```bash
git diff -- 'tinySOA/**/*.py'
git diff HEAD~1..HEAD -- 'tinySOA/**/*.py'
git log --oneline -5
```

### Sub-skill Mode

The caller provides the diff and context (requirement description, affected files).

**Record the full diff and file list for use in Phase 3.**

## Phase 2: Impact Assessment

Map each changed file to its subpackage and check cross-package dependencies:

| File Pattern | Subpackage | Risk |
|---|---|---|
| `core/model.py`, `core/errors.py` | domain model, exception hierarchy | **HIGH** |
| `api/*.py` | ABC contracts (Registry/Invoker/Publisher/Subscriber) | **HIGH** |
| `eventbus/bus.py` | `EventBus` ABC (the protocol-stack seam) | **HIGH** |
| `eventbus/someip.py` | SOME/IP protocol stack (depends on pysomeip) | **HIGH** |
| `eventbus/tcp.py` | TCP protocol stack (dev/demo) | **MEDIUM** |
| `eventbus/message.py` | `EventMessage` shape | **MEDIUM** |
| `runtime/*.py` | Container, LifecycleManager | **HIGH** |
| `spi/*.py` | Interceptor/Plugin (cross-cutting) | **MEDIUM** |
| `policies/*.py` | Retry/Timeout/CircuitBreaker | **MEDIUM** |
| `obs/*.py` | Metrics/Tracing | **LOW** |
| `config/*.py` | ConfigLoader/Config | **MEDIUM** |
| `examples/*.py` | demos | **LOW** |
| `tests/*.py` | test suite | **LOW** |

**Check for cross-package impact**: changes to `core/model.py` (Service/ServiceStatus) ripple into `runtime/`, `api/`, `eventbus/`. Changes to the `EventBus` ABC affect ALL three protocol stacks. Changes to the error hierarchy affect everyone.

**Estimate blast radius**:
```bash
grep -rn "from tinysoa.core.model import\|from tinysoa.eventbus.bus import\|from tinysoa.core.errors import" tinySOA/src/ | wc -l
```

## Phase 3: Three-Agent Parallel Adversarial Review

**CRITICAL: Spawn all three agents simultaneously using parallel Agent tool calls. Each agent MUST receive the full diff and context.**

### Agent 1: Red Team (subagent_type: general-purpose)

**Prompt template for Red Team agent:**

```
You are a RED TEAM code reviewer for the tinySOA project (a Python SOA framework). Your job is to ATTACK the following code changes and find EVERY possible problem. Be aggressive, be thorough, be skeptical.

## Changed Files
{FULL DIFF AND FILE LIST}

## Impact Assessment
{FROM PHASE 2: subpackages affected, cross-package dependencies, blast radius}

## Your Attack Vectors — Check EVERY One

### A. Python Style & Type Safety
1. [ ] 4-space indent; no tabs; no trailing whitespace
2. [ ] `from __future__ import annotations` in new modules
3. [ ] Public functions/methods fully annotated (params + return)
4. [ ] No unjustified `Any` in public signatures
5. [ ] black/ruff clean; mypy clean (if available)
6. [ ] No star imports; no mutable default args

### B. SOA Correctness (the core of this framework)
7. [ ] `ServiceStatus` transitions go ONLY through the guarded `transition()`; no direct `status=` mutation; illegal transitions raise `StateError`
8. [ ] New `EventBus` implementation overrides ALL 4 abstract methods (publish/subscribe/unsubscribe/get_subscribers_count) with correct semantics
9. [ ] Interceptor `priority` is honoured by the chain ordering (lower = earlier)
10. [ ] Topic matching semantics are consistent (`matches`/`match_any`) — subscribe/publish use the same matcher
11. [ ] Lifecycle: start/stop/terminate are idempotent-safe and clean up resources
12. [ ] Container add/remove keeps running-set consistent

### C. Async & Resource Safety
13. [ ] No blocking I/O inside async code (no `time.sleep`, blocking sockets, requests)
14. [ ] `asyncio.CancelledError` never swallowed; broad `except Exception` re-raises it
15. [ ] `create_task` results are retained (no GC'd fire-and-forget)
16. [ ] Transports/sockets/tasks closed/cancelled on ALL paths (incl. error + teardown)
17. [ ] Shared mutable state (subscribers, instances) protected by asyncio primitives

### D. Correctness Bugs
18. [ ] Exception paths clean up ALL resources
19. [ ] Race conditions on shared bus/registry state
20. [ ] Off-by-one / wrong key in topic↔eventgroup mapping
21. [ ] `EventMessage` fields (topic/payload/correlation_id/trace_id) populated consistently
22. [ ] No swallowed errors that hide framework failures

### E. Protocol-Stack Correctness (ONLY if change touches eventbus/someip.py or tcp.py)
23. [ ] (someip.py) SOME/IP wire fields big-endian (`>`/`!`)
24. [ ] (someip.py) `session_id` assigned on request, echoed on response
25. [ ] (someip.py) topic↔eventgroup mapping bidirectional & consistent
26. [ ] (someip.py) multicast used for SD, unicast for method/event — chosen correctly
27. [ ] (tcp.py) server/client transports closed on error/teardown

### F. tinySOA Project Specifics
28. [ ] Code placed under correct subpackage (core/api/spi/eventbus/runtime/policies/obs/config)
29. [ ] Tests use pytest + pytest-asyncio (not unittest)
30. [ ] No logic duplicated from pysomeip — reuses `someip.*`
31. [ ] Framework errors (`core/errors.py`) used for framework failures (not bare built-ins)
32. [ ] Examples still run via `PYTHONPATH=src python examples/...`

## Output Format

For EACH finding, output EXACTLY this format:

### Finding #[N]: [SHORT TITLE]
- **Severity**: CRITICAL / WARNING / INFO
- **Category**: [A1|B7|C13|D18|E23|F28...]
- **Location**: `file.py:line_number` (or approximate)
- **Description**: [What is wrong]
- **Attack scenario**: [How this could cause a state-machine corruption, event loss, resource leak, or protocol desync]
- **Suggested fix**: [Specific code change to resolve]

After all findings, provide a summary:

### Red Team Summary
- Total findings: N
- CRITICAL: N
- WARNING: N
- INFO: N
- Most dangerous finding: [describe]
```

### Agent 2: Blue Team (subagent_type: general-purpose)

**Prompt template for Blue Team agent:**

```
You are a BLUE TEAM code defender for the tinySOA project. Your job is to VERIFY the correctness of the following code changes. You are NOT rubber-stamping — you must actively trace every code path and confirm or challenge each behaviour.

## Changed Files
{FULL DIFF AND FILE LIST}

## Requirement Context
{FROM CALLER: what this code is supposed to do}

## Impact Assessment
{FROM PHASE 2: subpackages affected, dependencies}

## Your Defence Vectors — Verify EACH One

### A. Requirement Coverage
1. [ ] Does the code implement ALL aspects of the stated requirement?
2. [ ] Are edge cases handled (empty topics, duplicate subscribe, full lifecycle cycle)?
3. [ ] Correct behaviour for error conditions in the requirement?

### B. SOA Compliance
4. [ ] ServiceStatus transitions are legal and guarded?
5. [ ] EventBus impl satisfies the ABC contract (all 4 methods, correct semantics)?
6. [ ] Interceptor chain preserves ordering and error propagation?
7. [ ] Lifecycle start/stop/terminate correct and resource-safe?
8. [ ] Topic matching consistent between publish and subscribe?

### C. Correctness Verification
9. [ ] Trace EVERY exception path: each cleans up ALL resources (transports/tasks/subscriptions)
10. [ ] Trace the happy path: correct value, correct await chain, correct state transition
11. [ ] Verify async lifecycle: transports closed, tasks awaited, CancelledError re-raised
12. [ ] Verify shared-state synchronization (subscribers, instances, registry)

### D. Build and Integration
13. [ ] Imports cleanly (`PYTHONPATH=src python -c "import tinysoa.<pkg>"`)?
14. [ ] Tests pass: `cd tinySOA && PYTHONPATH=$PWD/src pytest -q tests`?
15. [ ] mypy/ruff clean (if available)?
16. [ ] Examples still run?

### E. Positive Findings
17. [ ] What does the code do RIGHT? (clean ABC design, thorough typing, good async hygiene)
18. [ ] Which tinySOA conventions are followed correctly?
19. [ ] Is the code well-structured and maintainable?

## Output Format

### Verified Correct
- [Category] [File:line] — [What was verified and how]

### Potential Concerns
- [Category] [File:line] — [Concern description and why it might matter]

### Positive Findings
- [What the code does right, good patterns observed]

### Overall Quality Assessment
- **Quality Score**: X / 10
- **Justification**: [Why this score]
- **Strengths**: [List]
- **Weaknesses**: [List]
- **Missing Coverage**: [What tests are absent]
```

### Agent 3: Constraint Verification (subagent_type: general-purpose)

**Prompt template for Constraint Verification agent:**

```
You are a tinySOA constraint enforcer. Perform a systematic constraint check on every changed file.

## Changed Files
{FULL DIFF AND FILE LIST}

## 25-Item Constraint Checklist

For EACH file, check EVERY constraint and output a table:

### [filename]
| # | Constraint | Status | Line(s) | Detail |
|---|-----------|--------|---------|--------|
| A1 | 4-space indentation (no tabs) | PASS/FAIL | — | [or tabs] |
| A2 | from __future__ import annotations | PASS/FAIL | — | [or missing] |
| A3 | Public APIs fully annotated | PASS/FAIL | — | [or untyped] |
| A4 | black/ruff clean (if available) | PASS/FAIL | — | [or issues] |
| A5 | mypy clean (if available) | PASS/FAIL | — | [or errors] |
| B1 | ServiceStatus via guarded transition() | PASS/FAIL | — | [or direct status=] |
| B2 | EventBus impl overrides all 4 methods | PASS/FAIL | — | [or missing] |
| B3 | Interceptor priority honoured | PASS/FAIL | — | [or wrong order] |
| B4 | Topic matching consistent | PASS/FAIL | — | [or mismatch] |
| B5 | Lifecycle idempotent + resource-safe | PASS/FAIL | — | [or leak] |
| B6 | Framework errors used (core/errors.py) | PASS/FAIL | — | [or bare built-ins] |
| C1 | No broad except / CancelledError swallowed | PASS/FAIL | — | [or swallowed] |
| C2 | No blocking I/O in async | PASS/FAIL | — | [or blocking call] |
| C3 | create_task results retained | PASS/FAIL | — | [or fire-and-forget] |
| C4 | Resources closed on ALL paths | PASS/FAIL | — | [or leak] |
| C5 | Shared state synchronized | PASS/FAIL | — | [or race] |
| D1 | EventMessage fields consistent | PASS/FAIL | — | [or missing fields] |
| D2 | Exception paths clean up resources | PASS/FAIL | — | [or leak] |
| E1 | (someip) wire big-endian | PASS/FAIL | — | [n/a if not someip.py] |
| E2 | (someip) session_id echoed | PASS/FAIL | — | [n/a if not someip.py] |
| E3 | (someip) topic↔eventgroup mapping | PASS/FAIL | — | [n/a if not someip.py] |
| E4 | (tcp) transports closed on teardown | PASS/FAIL | — | [n/a if not tcp.py] |
| F1 | Code under correct subpackage | PASS/FAIL | — | [or wrong location] |
| F2 | Tests use pytest/pytest-asyncio | PASS/FAIL | — | [or unittest] |

### Per-File Summary
- File: [name]
- Violations: N critical, N warning, N info
- Overall: PASS/FAIL

### Overall Summary
- Total files checked: N
- Total violations: N
  - CRITICAL: N
  - WARNING: N
  - INFO: N
- Gate Result: PASS / FAIL
```

## Phase 4: Adversarial Debate and Consensus

After all three agents return, reconcile their findings:

### Reconciliation Rules

For EACH Red Team finding:

| Red Finding | Blue Response | Constraint Agent | Final Severity |
|---|---|---|---|
| CRITICAL | Unaddressed (Blue missed it) | FAIL | **CRITICAL** — must fix, BLOCK |
| CRITICAL | Acknowledged (Blue agrees) | FAIL/any | **CRITICAL** — must fix, BLOCK |
| CRITICAL | Defended (Blue proves it's OK) | PASS | **WARNING** — debatable, escalate |
| WARNING | Unaddressed | FAIL | **WARNING** — should fix |
| WARNING | Defended | PASS | **INFO** — debated |
| INFO | Any | Any | **INFO** — noted |

### Scoring

```
CRITICAL = 0 points
WARNING  = 1 point
INFO     = 2 points
PASS     = 3 points

Average score across all findings = consensus_score

Gate rules:
  ANY CRITICAL finding          → BLOCK (consensus_score = 0)
  3+ WARNING findings           → BLOCK (consensus_score < 2.5)
  All INFO/PASS                 → PASS  (consensus_score >= 2.5)
```

## Phase 5: Consensus Report

Output the final report:

```
## Red-Blue Adversarial Review — Consensus Report

### Review Scope
- Files reviewed: [list]
- Subpackages affected: [list]
- Cross-package dependencies: [description]
- Blast radius: [description]

### Statistics
- Red Team findings: N (C: N, W: N, I: N)
- Blue Team verified: N items
- Constraint violations: N (C: N, W: N, I: N)
- Reconciled findings: N

### CRITICAL Findings (MUST FIX — BLOCK)
[For each:]
#### Finding #[N]: [Title]
- **Category**: [B7|C1|E1|...]
- **Location**: `file.py:line`
- **Red Team**: [attack description]
- **Blue Team**: [unaddressed/acknowledged/defended]
- **Constraint Agent**: PASS/FAIL
- **Final verdict**: CRITICAL
- **Fix required**: [specific code change]

### WARNING Findings (SHOULD FIX)
[Same format as above]

### INFO / Debated Findings
[Same format, with note on why debated]

### Verified Correct (Blue Team)
[Summary of what Blue confirmed is correct]

### Consensus Decision
- **Consensus Score**: X.X / 3.0
- **Gate Result**: PASS / BLOCK
- **Required Actions Before Proceeding**:
  1. [Fix finding #N]
  2. [Fix finding #M]

### Recommended Next Steps
[What the calling skill should do next]
```

## EVOLUTION_REPORT

```
EVOLUTION_REPORT {
  skill: "tinysoa-review"
  task_summary: "Red-blue review of N files"
  findings: { critical: N, warning: N, info: N }
  constraint_violations: { A: N, B: N, C: N, D: N, E: N, F: N }
  most_common_violation_type: "..."
  false_positives: N
  consensus_score: X.X
  gate_result: "PASS" | "BLOCK"
  iteration_count: N
}
```
