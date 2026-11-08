#!/bin/bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

python=(python3)
imports='import pandas, plotly, pydantic, streamlit'
if [[ "${1:-}" == cli ]]; then
    imports='import pandas'
fi
if [[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] &&
    ! python3 -B -c "$imports" >/dev/null 2>&1; then
    python=(arch -x86_64 python3)
fi

if [[ "${1:-}" == cli ]]; then
    shift
    exec "${python[@]}" -B engine.py "$@"
fi

echo "Starting Tangerine Mission Control on http://localhost:8501 ..."
exec "${python[@]}" -B -m streamlit run app.py "$@"
