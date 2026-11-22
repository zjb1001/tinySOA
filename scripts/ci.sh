#!/usr/bin/env bash
# Local CI runner for tinySOA.
#
# Default policy (see docs/ci-cd.md):
#   * pytest          -> blocking
#   * ruff / black    -> advisory
#   * mypy            -> advisory
#   * examples smoke  -> opt-in (--with-smoke / --smoke-only)
#
# Usage:
#   bash scripts/ci.sh                  # tests + advisory quality checks
#   bash scripts/ci.sh --strict         # advisory failures also fail the run
#   bash scripts/ci.sh --tests-only
#   bash scripts/ci.sh --lint-only
#   bash scripts/ci.sh --typecheck-only
#   bash scripts/ci.sh --smoke-only
#   bash scripts/ci.sh --with-smoke
#   bash scripts/ci.sh --coverage
#
# Environment:
#   PYTHON   Python interpreter to use (default: .venv/bin/python, else python3)
#   CI_ROOT  Repository root to test (default: parent of this script)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${CI_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
        PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
    else
        PYTHON_BIN="$(command -v python3 || true)"
    fi
fi
if [[ -z "$PYTHON_BIN" ]]; then
    echo "ci: python3 not found (set PYTHON=/path/to/python)" >&2
    exit 127
fi

export PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/third_party/pysomeip/src${PYTHONPATH:+:$PYTHONPATH}"

RUN_TESTS=1
RUN_LINT=1
RUN_TYPE=1
RUN_SMOKE=0
STRICT=0
COVERAGE=0

usage() {
    sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
    case "$arg" in
        --tests-only)
            RUN_TESTS=1; RUN_LINT=0; RUN_TYPE=0; RUN_SMOKE=0 ;;
        --lint-only)
            RUN_TESTS=0; RUN_LINT=1; RUN_TYPE=0; RUN_SMOKE=0 ;;
        --typecheck-only)
            RUN_TESTS=0; RUN_LINT=0; RUN_TYPE=1; RUN_SMOKE=0 ;;
        --smoke-only)
            RUN_TESTS=0; RUN_LINT=0; RUN_TYPE=0; RUN_SMOKE=1 ;;
        --with-smoke)
            RUN_SMOKE=1 ;;
        --strict)
            STRICT=1 ;;
        --coverage)
            COVERAGE=1 ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            echo "ci: unknown argument: $arg (use --help)" >&2
            exit 2 ;;
    esac
done

SUMMARY=()
FAILED=0
ADVISORY_FAILED=0

record() {
    SUMMARY+=("$1")
}

run_blocking() {
    local name="$1"
    shift
    echo ""
    echo "==> $name"
    if "$@"; then
        record "PASS  $name"
    else
        record "FAIL  $name"
        FAILED=1
    fi
}

run_advisory() {
    local name="$1"
    shift
    echo ""
    echo "==> $name (advisory)"
    if "$@"; then
        record "PASS  $name"
    else
        record "WARN  $name"
        ADVISORY_FAILED=1
    fi
}

python_has() {
    "$PYTHON_BIN" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)' "$1" >/dev/null 2>&1
}

if [[ "$RUN_TESTS" == "1" ]]; then
    if [[ ! -d "$ROOT_DIR/tests" ]]; then
        echo "ci: tests/ not found under $ROOT_DIR" >&2
        exit 1
    fi
    if [[ "$COVERAGE" == "1" ]]; then
        if python_has pytest_cov; then
            run_blocking "pytest (coverage)" \
                "$PYTHON_BIN" -m pytest tests -q \
                --cov=src/tinysoa --cov-report=term-missing --cov-report=xml
        else
            record "SKIP  coverage (pytest-cov not installed)"
            run_blocking "pytest" "$PYTHON_BIN" -m pytest tests -q
        fi
    else
        run_blocking "pytest" "$PYTHON_BIN" -m pytest tests -q
    fi
fi

if [[ "$RUN_LINT" == "1" ]]; then
    if python_has ruff; then
        run_advisory "ruff" "$PYTHON_BIN" -m ruff check src tests examples
    elif command -v ruff >/dev/null 2>&1; then
        run_advisory "ruff" ruff check src tests examples
    else
        record "SKIP  ruff (not installed)"
    fi

    if python_has black; then
        run_advisory "black" \
            "$PYTHON_BIN" -m black --check --diff \
            --exclude '/(\.venv|\.agent-flow|third_party)/' src tests examples
    elif command -v black >/dev/null 2>&1; then
        run_advisory "black" \
            black --check --diff \
            --exclude '/(\.venv|\.agent-flow|third_party)/' src tests examples
    else
        record "SKIP  black (not installed)"
    fi
fi

if [[ "$RUN_TYPE" == "1" ]]; then
    if python_has mypy; then
        run_advisory "mypy" "$PYTHON_BIN" -m mypy --show-error-codes src/tinysoa
    elif command -v mypy >/dev/null 2>&1; then
        run_advisory "mypy" mypy --show-error-codes src/tinysoa
    else
        record "SKIP  mypy (not installed)"
    fi
fi

if [[ "$RUN_SMOKE" == "1" ]]; then
    run_blocking "examples smoke" \
        env PYTHON="$PYTHON_BIN" make -C "$ROOT_DIR/examples" \
        smoke-vdp smoke-calc smoke-pubsub smoke-multipub
fi

echo ""
echo "================ CI summary ================"
if [[ ${#SUMMARY[@]} -gt 0 ]]; then
    printf '  %s\n' "${SUMMARY[@]}"
fi
echo "============================================"

if [[ "$FAILED" -ne 0 ]]; then
    echo "ci: FAILED (blocking gate)"
    exit 1
fi
if [[ "$STRICT" == "1" && "$ADVISORY_FAILED" -ne 0 ]]; then
    echo "ci: FAILED (--strict: advisory gate promoted to blocking)"
    exit 1
fi
echo "ci: PASS"
exit 0
