#!/bin/bash
# Convenient runner for Tangerine Resilience Engine
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ "$1" == "cli" ]; then
    shift
    arch -x86_64 python3 engine.py "$@"
else
    echo "Starting Tangerine Resilience Engine Web App on http://localhost:8501 ..."
    arch -x86_64 python3 -m streamlit run app.py "$@"
fi
