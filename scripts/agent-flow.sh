#!/usr/bin/env bash
# Local agent flow: issue/task -> isolated worktree -> implement -> CI -> review -> PR.
#
# This is the local CI/CD + agent scaffold for tinySOA. It never edits the main
# working tree: every run gets its own git worktree and branch.
#
# Usage:
#   bash scripts/agent-flow.sh --issue 123
#   bash scripts/agent-flow.sh --issue 123 --yes
#   bash scripts/agent-flow.sh --task "Add DDS topology notes" --title "DDS notes"
#   bash scripts/agent-flow.sh --issue 123 --dry-run
#
# Flags:
#   --issue N          GitHub issue number (uses `gh issue view`)
#   --task TEXT        Free-form task instead of an issue
#   --title TEXT       Title for --task (default: first line of --task)
#   --base BRANCH      PR base branch (default: main)
#   --base-ref REF     Git ref for the worktree/diff (default: origin/<base>)
#   --max-repair N     Repair cycles after CI/review failure (default: 2)
#   --yes              Push the branch and open a PR (required for outward actions)
#   --no-pr            Run everything locally; do not push or open a PR
#   --dry-run          Print the plan and exit
#   --keep-worktree    Keep the worktree after a successful run
#   --help             Show this help
#
# Environment (agent-agnostic):
#   PYTHON            Python for prompt rendering (default: .venv/bin/python, else python3)
#   AGENT_CMD         REQUIRED command for the implementation stage
#   AGENT_REVIEW_CMD  Optional review command (default: AGENT_CMD)
#   AGENT_REPAIR_CMD  Optional repair command (default: AGENT_CMD)
#   AGENT_ATTRIBUTION Optional commit/PR trailer (e.g. a Co-Authored-By line)
#
# The agent command is executed with cwd = the run's worktree and receives:
#   AGENT_STAGE=implement|review|repair
#   AGENT_PROMPT_FILE=<absolute path to the rendered prompt>
#   AGENT_WORKTREE=<absolute path>
#   AGENT_RUN_DIR=<absolute path for artifacts>
#   AGENT_LOG_FILE=<absolute path for its own log>
#   AGENT_READ_ONLY=0|1
#   PYTHON=<interpreter>  PYTHONPATH=<worktree src paths>
# Exit code 0 means success; stdout/stderr are captured to AGENT_LOG_FILE.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROMPTS_DIR="$SCRIPT_DIR/agent-flow/prompts"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
        PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
    else
        PYTHON_BIN="$(command -v python3 || true)"
    fi
fi
AGENT_CMD="${AGENT_CMD:-}"
AGENT_REVIEW_CMD="${AGENT_REVIEW_CMD:-$AGENT_CMD}"
AGENT_REPAIR_CMD="${AGENT_REPAIR_CMD:-$AGENT_CMD}"

ISSUE=""
TASK_TEXT=""
TASK_TITLE=""
BASE="main"
BASE_REF=""
MAX_REPAIR=2
ASSUME_YES=0
NO_PR=0
DRY_RUN=0
KEEP_WORKTREE=0

SUCCESS=0
WORKTREE=""
RUN_DIR=""
BRANCH=""

usage() {
    sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

die() {
    echo "agent-flow: $*" >&2
    exit 1
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        die "required command not found: $1"
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --issue)
            [[ $# -ge 2 ]] || die "--issue needs a number"
            ISSUE="$2"; shift 2 ;;
        --task)
            [[ $# -ge 2 ]] || die "--task needs text"
            TASK_TEXT="$2"; shift 2 ;;
        --title)
            [[ $# -ge 2 ]] || die "--title needs text"
            TASK_TITLE="$2"; shift 2 ;;
        --base)
            [[ $# -ge 2 ]] || die "--base needs a branch"
            BASE="$2"; shift 2 ;;
        --base-ref)
            [[ $# -ge 2 ]] || die "--base-ref needs a git ref"
            BASE_REF="$2"; shift 2 ;;
        --max-repair)
            [[ $# -ge 2 ]] || die "--max-repair needs a number"
            MAX_REPAIR="$2"; shift 2 ;;
        --yes)
            ASSUME_YES=1; shift ;;
        --no-pr)
            NO_PR=1; shift ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --keep-worktree)
            KEEP_WORKTREE=1; shift ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            die "unknown argument: $1 (use --help)" ;;
    esac
done

if [[ -n "$ISSUE" && -n "$TASK_TEXT" ]]; then
    die "use either --issue or --task, not both"
fi
if [[ -z "$ISSUE" && -z "$TASK_TEXT" ]]; then
    usage
    exit 2
fi
if [[ ! "$MAX_REPAIR" =~ ^[0-9]+$ ]]; then
    die "--max-repair must be a non-negative integer"
fi
BASE_REF="${BASE_REF:-origin/$BASE}"

if [[ -z "$PYTHON_BIN" ]]; then
    die "python3 not found (set PYTHON=/path/to/python)"
fi

require_cmd git
if [[ "$DRY_RUN" == "0" ]]; then
    if [[ -n "$ISSUE" || ( "$ASSUME_YES" == "1" && "$NO_PR" == "0" ) ]]; then
        require_cmd gh
    fi
    if [[ -z "$AGENT_CMD" ]]; then
        die "AGENT_CMD is not set; define your agent adapter (see docs/agent-flow.md)"
    fi
fi

if ! git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "not a git worktree: $ROOT_DIR"
fi

if [[ "$DRY_RUN" == "0" && "$ASSUME_YES" == "1" && "$NO_PR" == "0" ]]; then
    gh auth status >/dev/null 2>&1 || die "gh is not authenticated (run: gh auth login)"
fi

# ---------------------------------------------------------------- context ---
if [[ -n "$ISSUE" ]]; then
    if [[ "$DRY_RUN" == "0" ]]; then
        gh auth status >/dev/null 2>&1 || die "gh is not authenticated (run: gh auth login)"
        ISSUE_JSON="$(gh issue view "$ISSUE" --json number,title,body,url,state,labels)" \
            || die "cannot read issue #$ISSUE"
        ISSUE_TITLE="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["title"])' <<<"$ISSUE_JSON")"
        ISSUE_BODY="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin).get("body") or "")' <<<"$ISSUE_JSON")"
        ISSUE_URL="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["url"])' <<<"$ISSUE_JSON")"
        ISSUE_STATE="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["state"])' <<<"$ISSUE_JSON")"
        ISSUE_LABELS="$("$PYTHON_BIN" -c 'import json,sys; print(",".join(l["name"] for l in json.load(sys.stdin).get("labels", [])))' <<<"$ISSUE_JSON")"
        [[ "${ISSUE_STATE^^}" == "OPEN" ]] || die "issue #$ISSUE is not open (state=$ISSUE_STATE)"
        case ",$ISSUE_LABELS," in
            *,no-agent,*|*,agent-flow-skip,*)
                die "issue #$ISSUE is marked no-agent/agent-flow-skip" ;;
        esac
    else
        ISSUE_TITLE="issue-$ISSUE"
        ISSUE_BODY=""
        ISSUE_URL=""
    fi
    TITLE="$ISSUE_TITLE"
    SOURCE="issue #$ISSUE"
else
    TITLE="${TASK_TITLE:-$(printf '%s' "$TASK_TEXT" | head -n 1)}"
    ISSUE_TITLE="$TITLE"
    ISSUE_BODY="$TASK_TEXT"
    ISSUE_URL="(local task)"
    TITLE="$ISSUE_TITLE"
    SOURCE="local task"
fi

[[ -n "$TITLE" ]] || die "empty title"

SLUG="$("$PYTHON_BIN" -c 'import re,sys; s=sys.argv[1].lower(); print(re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "task")' "$TITLE")"
STAMP="$(date +%Y%m%d-%H%M%S)"
RUN_ID="${STAMP}-${SLUG}"
if [[ -n "$ISSUE" ]]; then
    BRANCH="agent/issue-${ISSUE}-${SLUG}-${STAMP}"
else
    BRANCH="agent/${SLUG}-${STAMP}"
fi

RUN_DIR="$ROOT_DIR/.agent-flow/runs/$RUN_ID"
WORKTREE="$ROOT_DIR/.agent-flow/worktrees/$RUN_ID"

echo "agent-flow: $SOURCE -> $BRANCH"
echo "  base:      $BASE_REF (PR base: $BASE)"
echo "  run dir:   $RUN_DIR"
echo "  worktree:  $WORKTREE"
echo "  max repair: $MAX_REPAIR"

if [[ "$DRY_RUN" == "1" ]]; then
    echo "agent-flow: dry run; no changes made"
    exit 0
fi

mkdir -p "$RUN_DIR" "$ROOT_DIR/.agent-flow/worktrees"

cleanup() {
    local rc=$?
    trap - EXIT
    if [[ "$rc" -ne 0 ]]; then
        echo "agent-flow: failed (rc=$rc)" >&2
        echo "  logs:     $RUN_DIR" >&2
        [[ -d "$WORKTREE" ]] && echo "  worktree: $WORKTREE (kept for inspection)" >&2
    elif [[ "$SUCCESS" == "1" && "$KEEP_WORKTREE" == "0" && -d "$WORKTREE" ]]; then
        git -C "$ROOT_DIR" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
    fi
    exit "$rc"
}
trap cleanup EXIT

# ---------------------------------------------------------------- worktree ---
if [[ "$BASE_REF" == origin/* ]]; then
    git -C "$ROOT_DIR" fetch origin "${BASE_REF#origin/}" >/dev/null 2>&1 \
        || die "git fetch origin ${BASE_REF#origin/} failed"
fi
git -C "$ROOT_DIR" rev-parse --verify "$BASE_REF" >/dev/null 2>&1 \
    || die "base ref does not exist: $BASE_REF"
git -C "$ROOT_DIR" worktree add -b "$BRANCH" "$WORKTREE" "$BASE_REF" \
    || die "cannot create worktree at $WORKTREE"
if [[ -f "$WORKTREE/.gitmodules" ]]; then
    git -C "$WORKTREE" submodule update --init --recursive >/dev/null 2>&1 \
        || die "cannot initialize submodules in $WORKTREE"
fi

MAIN_PYTHON="$PYTHON_BIN"
WORKTREE_PYTHONPATH="$WORKTREE/src:$WORKTREE/third_party/pysomeip/src"

{
    printf '# %s\n\n' "$ISSUE_TITLE"
    printf -- '- Source: %s\n' "$ISSUE_URL"
    printf -- '- Branch: %s\n' "$BRANCH"
    printf -- '- Base: %s\n\n' "$BASE_REF"
    printf '## Body\n\n%s\n' "$ISSUE_BODY"
} > "$RUN_DIR/task.md"

render_prompt() {
    local template="$1"
    local output="$2"
    "$PYTHON_BIN" "$SCRIPT_DIR/render_prompt.py" "$template" "$output" \
        || die "cannot render prompt: $template"
}

run_agent() {
    local prompt_file="$1"
    local log_file="$2"
    local stage="$3"
    local read_only="$4"
    local command="$5"
    if [[ -z "$command" ]]; then
        die "no agent command configured for stage: $stage"
    fi
    echo "  agent: $stage (read_only=$read_only)" >&2
    (
        cd "$WORKTREE" || exit 1
        AGENT_STAGE="$stage" \
        AGENT_PROMPT_FILE="$prompt_file" \
        AGENT_WORKTREE="$WORKTREE" \
        AGENT_RUN_DIR="$RUN_DIR" \
        AGENT_LOG_FILE="$log_file" \
        AGENT_READ_ONLY="$read_only" \
        PYTHON="$MAIN_PYTHON" \
        PYTHONPATH="$WORKTREE_PYTHONPATH" \
            bash -c "$command"
    ) >"$log_file" 2>&1
}

export ISSUE_TITLE ISSUE_BODY ISSUE_URL BRANCH BASE BASE_REF WORKTREE RUN_DIR

# ------------------------------------------------------------ implement ---
echo "agent-flow: implementation"
render_prompt "$PROMPTS_DIR/implement.md" "$RUN_DIR/implement.prompt.md"
if ! run_agent "$RUN_DIR/implement.prompt.md" "$RUN_DIR/implement.log" implement 0 "$AGENT_CMD"; then
    die "implementation agent failed; see $RUN_DIR/implement.log"
fi
if [[ -z "$(git -C "$WORKTREE" status --porcelain)" ]]; then
    die "implementation agent produced no changes"
fi

# -------------------------------------------------------- CI + review ---
CI_LOG=""
REVIEW_LOG=""
VERDICT="UNKNOWN"
FINAL_CYCLE=0
CI_OK=0

for ((cycle = 0; cycle <= MAX_REPAIR; cycle++)); do
    FINAL_CYCLE=$cycle
    CI_LOG="$RUN_DIR/ci-$cycle.log"
    echo "agent-flow: CI cycle $cycle"
    if ( cd "$WORKTREE" && PYTHON="$MAIN_PYTHON" bash "$WORKTREE/scripts/ci.sh" ) >"$CI_LOG" 2>&1; then
        echo "  CI: PASS"
        CI_OK=1
    else
        echo "  CI: FAIL"
        CI_OK=0
        if (( cycle == MAX_REPAIR )); then
            break
        fi
        FAILURE_LOG="$(tail -n 120 "$CI_LOG")"
        export FAILURE_LOG
        render_prompt "$PROMPTS_DIR/repair.md" "$RUN_DIR/repair-$cycle.prompt.md"
        if ! run_agent "$RUN_DIR/repair-$cycle.prompt.md" "$RUN_DIR/repair-$cycle.log" repair 0 "$AGENT_REPAIR_CMD"; then
            die "repair agent failed; see $RUN_DIR/repair-$cycle.log"
        fi
        continue
    fi

    # Stage everything so the reviewer sees new files as well as edits.
    git -C "$WORKTREE" add -A
    DIFF_PATH="$RUN_DIR/review-$cycle.diff"
    git -C "$WORKTREE" diff --cached "$BASE_REF" > "$DIFF_PATH"
    export DIFF_PATH
    REVIEW_LOG="$RUN_DIR/review-$cycle.log"
    echo "agent-flow: review cycle $cycle"
    render_prompt "$PROMPTS_DIR/review.md" "$RUN_DIR/review-$cycle.prompt.md"
    if ! run_agent "$RUN_DIR/review-$cycle.prompt.md" "$REVIEW_LOG" review 1 "$AGENT_REVIEW_CMD"; then
        die "review agent failed; see $REVIEW_LOG"
    fi
    VERDICT="$(grep -Eo 'VERDICT: (PASS|BLOCK)' "$REVIEW_LOG" | tail -n 1 | sed 's/.*VERDICT: //')"
    VERDICT="${VERDICT:-UNKNOWN}"
    echo "  review: $VERDICT"

    if [[ "$VERDICT" == "PASS" ]]; then
        break
    fi
    if [[ "$VERDICT" == "UNKNOWN" ]]; then
        echo "  warning: review produced no VERDICT line; continuing" >&2
        break
    fi
    if (( cycle == MAX_REPAIR )); then
        break
    fi

    FAILURE_LOG="$(tail -n 120 "$REVIEW_LOG")"
    export FAILURE_LOG
    render_prompt "$PROMPTS_DIR/repair.md" "$RUN_DIR/repair-review-$cycle.prompt.md"
    if ! run_agent "$RUN_DIR/repair-review-$cycle.prompt.md" "$RUN_DIR/repair-review-$cycle.log" repair 0 "$AGENT_REPAIR_CMD"; then
        die "review-repair agent failed; see $RUN_DIR/repair-review-$cycle.log"
    fi
done

if [[ "$CI_OK" != "1" ]]; then
    die "CI did not pass after $((MAX_REPAIR + 1)) cycle(s); see $CI_LOG"
fi
if [[ "$VERDICT" == "BLOCK" ]]; then
    die "review still BLOCK after $((MAX_REPAIR + 1)) cycle(s); see $REVIEW_LOG"
fi

# ------------------------------------------------------------- commit ---
echo "agent-flow: committing"
git -C "$WORKTREE" add -A
if git -C "$WORKTREE" diff --cached --quiet; then
    die "no staged changes to commit"
fi
COMMIT_BODY="Automated by scripts/agent-flow.sh (AGENT_CMD=${AGENT_CMD})."
if [[ -n "$ISSUE" ]]; then
    COMMIT_BODY="$COMMIT_BODY\n\nCloses #$ISSUE"
fi
COMMIT_ARGS=(-m "agent: $TITLE" -m "$(printf '%b' "$COMMIT_BODY")")
if [[ -n "${AGENT_ATTRIBUTION:-}" ]]; then
    COMMIT_ARGS+=(-m "$AGENT_ATTRIBUTION")
fi
git -C "$WORKTREE" commit "${COMMIT_ARGS[@]}" || die "git commit failed"

COMMIT_SHA="$(git -C "$WORKTREE" rev-parse --short HEAD)"
echo "  commit: $COMMIT_SHA"

# ------------------------------------------------------------- PR body ---
PR_TITLE="[agent] $TITLE"
if [[ ${#PR_TITLE} -gt 72 ]]; then
    PR_TITLE="${PR_TITLE:0:69}..."
fi

{
    echo "## Summary"
    echo
    if [[ -n "$ISSUE" ]]; then
        echo "Closes #$ISSUE."
        echo
    fi
    echo "Automated by \`scripts/agent-flow.sh\` on branch \`$BRANCH\`."
    echo
    echo "### Implementation"
    echo
    if [[ -s "$RUN_DIR/implement-summary.md" ]]; then
        cat "$RUN_DIR/implement-summary.md"
    else
        echo '```'
        tail -n 80 "$RUN_DIR/implement.log"
        echo '```'
    fi
    echo
    echo "### CI"
    echo
    echo "Blocking gates: **PASS** (tests + ruff + black + mypy)."
    echo
    echo '```'
    if grep -q "CI summary" "$CI_LOG"; then
        sed -n '/CI summary/,$p' "$CI_LOG"
    else
        tail -n 40 "$CI_LOG"
    fi
    echo '```'
    echo
    echo "### Independent review"
    echo
    echo "Verdict: **$VERDICT** (repair cycles used: $FINAL_CYCLE)"
    echo
    echo '```'
    tail -n 60 "$REVIEW_LOG"
    echo '```'
    echo
    if [[ -n "${AGENT_ATTRIBUTION:-}" ]]; then
        echo "$AGENT_ATTRIBUTION"
    else
        echo "Generated by \`scripts/agent-flow.sh\`."
    fi
} > "$RUN_DIR/pr-body.md"

SUCCESS=1

if [[ "$ASSUME_YES" == "0" || "$NO_PR" == "1" ]]; then
    KEEP_WORKTREE=1
    echo "agent-flow: local verification complete"
    echo "  branch:   $BRANCH"
    echo "  worktree: $WORKTREE"
    echo "  PR body:  $RUN_DIR/pr-body.md"
    if [[ "$NO_PR" == "1" ]]; then
        echo "  --no-pr: not pushing"
    else
        echo "  re-run with --yes to push and open a PR"
    fi
    exit 0
fi

echo "agent-flow: pushing $BRANCH"
git -C "$WORKTREE" push -u origin "$BRANCH" || die "git push failed"

echo "agent-flow: opening PR"
PR_URL="$( cd "$WORKTREE" && gh pr create \
    --base "$BASE" \
    --head "$BRANCH" \
    --title "$PR_TITLE" \
    --body-file "$RUN_DIR/pr-body.md" )" || die "gh pr create failed"

echo "agent-flow: PR ready: $PR_URL"
echo "  logs: $RUN_DIR"
exit 0
