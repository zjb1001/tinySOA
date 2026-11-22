#!/usr/bin/env bash
# Local CI runner for tinySOA.
#
# Default policy (see docs/ci-cd.md):
#   * pytest          -> blocking
#   * ruff / black    -> blocking
#   * mypy            -> blocking
#   * examples smoke  -> opt-in (--with-smoke / --smoke-only)
#
# Usage:
#   bash scripts/ci.sh                  # tests + blocking quality checks
#   bash scripts/ci.sh --advisory       # tests block; quality checks warn only
#   bash scripts/ci.sh --strict         # alias for the default
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
STRICT=1
COVERAGE=0

usage() {
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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
        --advisory)
            STRICT=0 ;;
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

run_quality() {
    local name="$1"
    shift
    echo ""
    echo "==> $name"
    if "$@"; then
        record "PASS  $name"
    elif [[ "$STRICT" == "1" ]]; then
        record "FAIL  $name"
        FAILED=1
    else
        record "WARN  $name"
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
        run_quality "ruff" "$PYTHON_BIN" -m ruff check src tests examples
    elif command -v ruff >/dev/null 2>&1; then
        run_quality "ruff" ruff check src tests examples
    else
        record "SKIP  ruff (not installed)"
    fi

    if python_has black; then
        run_quality "black" \
            "$PYTHON_BIN" -m black --check --diff \
            --exclude '/(\.venv|\.agent-flow|third_party)/' src tests examples
    elif command -v black >/dev/null 2>&1; then
        run_quality "black" \
            black --check --diff \
            --exclude '/(\.venv|\.agent-flow|third_party)/' src tests examples
    else
        record "SKIP  black (not installed)"
    fi
fi

if [[ "$RUN_TYPE" == "1" ]]; then
    if python_has mypy; then
        run_quality "mypy" "$PYTHON_BIN" -m mypy --show-error-codes src/tinysoa
    elif command -v mypy >/dev/null 2>&1; then
        run_quality "mypy" mypy --show-error-codes src/tinysoa
    else
        record "SKIP  mypy (not installed)"
    fi
fi

if [[ "$RUN_SMOKE" == "1" ]]; then
    run_blocking "examples smoke" \
        env PYTHON="$PYTHON_BIN" make -C "$ROOT_DIR/examples" \
        smoke-vdp smoke-calc smoke-pubsub
fi

echo ""
echo "================ CI summary ================"
if [[ ${#SUMMARY[@]} -gt 0 ]]; then
    printf '  %s\n' "${SUMMARY[@]}"
fi
echo "============================================"

if [[ "$FAILED" -ne 0 ]]; then
    echo "ci: FAILED"
    exit 1
fi
echo "ci: PASS"
exit 0
