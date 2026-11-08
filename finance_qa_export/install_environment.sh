#!/usr/bin/env bash
set -euo pipefail
cd /workspace/tangerine_data
python3 -m venv /workspace/.venvs/tangerine
/workspace/.venvs/tangerine/bin/python -m pip install -r requirements.txt pytest openpyxl
/workspace/.venvs/tangerine/bin/python -m pip check
