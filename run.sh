#!/usr/bin/env bash
# Convenient runner for Tangerine Resilience Engine
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer the active Conda/virtual environment; also support systems with only python3.
PYTHON_BIN=""
for candidate in python python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Python 3.10+ is required. Activate your Conda/virtual environment or install Python 3." >&2
    exit 1
fi

if [ "${1:-}" == "cli" ]; then
    shift
    exec "$PYTHON_BIN" -B engine.py "$@"
else
    echo "Starting Tangerine Mission Control ..."
    exec "$PYTHON_BIN" -B -m streamlit run app.py "$@"
fi
