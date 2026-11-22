You are the **implementation stage** of tinySOA's local agent flow.

## Repository rules

- Use `README.md`, `design/`, and the existing tests as the source of truth for
  style and contracts.
- If the repository provides additional engineering guidance, follow it; this
  flow does not depend on any specific harness or agent.
- Keep the change minimal and scoped to the task. Do not refactor unrelated code.
- Add or update pytest tests for every behavior change.
- Do not commit, push, or open a pull request; the wrapper script handles that.
- Do not edit harness settings (`.claude/settings*.json`), generated logs, or
  `.agent-flow/` artifacts.
- If the task is ambiguous or unsafe, stop and write the question to
  `{{RUN_DIR}}/implement-summary.md` instead of guessing.

## Task

- Title: {{ISSUE_TITLE}}
- Source: {{ISSUE_URL}}
- Branch: {{BRANCH}}
- Base: {{BASE}}
- Worktree: {{WORKTREE}}

### Task body

{{ISSUE_BODY}}

## Verification

Prefer `bash scripts/ci.sh --tests-only` to run the test suite. If the local
environment lacks dependencies, report that instead of installing packages.

## Deliverable

1. Implement the task in the current worktree.
2. Add tests that would fail without the change.
3. Write a concise summary to `{{RUN_DIR}}/implement-summary.md` with:
   - What changed and why
   - Files touched
   - Tests added
   - Known limitations or follow-ups
4. End your response with a short summary of the change.
