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

case "${1:-web}" in
    cli)
        shift
        exec "$PYTHON_BIN" -B engine.py "$@"
        ;;
    streamlit|legacy)
        shift
        exec "$PYTHON_BIN" -B -m streamlit run app.py "$@"
        ;;
    web)
        if [ "$#" -gt 0 ]; then shift; fi
        ;;
    --help|-h)
        echo "Usage: bash run.sh [web|streamlit|cli] [arguments]"
        echo "Default: website at http://127.0.0.1:8000 (Python API + browser frontend)"
        echo "Examples: bash run.sh --port 8001 | bash run.sh streamlit --server.port 8502"
        exit 0
        ;;
esac

if ! "$PYTHON_BIN" -c 'import fastapi, uvicorn, pandas, numpy, pydantic, requests' >/dev/null 2>&1; then
    echo "Website dependencies are missing from the active Python environment." >&2
    echo "Run: $PYTHON_BIN -m pip install -r requirements-web.txt" >&2
    exit 1
fi

echo "Starting Tangerine Resilience Workspace (default: http://127.0.0.1:8000) ..."
exec "$PYTHON_BIN" -B -m uvicorn web_app.server:app --host 127.0.0.1 --port 8000 --workers 1 "$@"
