#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
venv="$repo_root/.venv"
python_command=${PYTHON:-python3.11}

if ! command -v "$python_command" >/dev/null 2>&1; then
    python_command=python3
fi

"$python_command" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "Python 3.11 oder neuer ist erforderlich.")'
"$python_command" -m venv "$venv"
"$venv/bin/python" -m pip install --upgrade pip
"$venv/bin/python" -m pip install -e "$repo_root"
"$venv/bin/python" -m unittest discover -s "$repo_root/tests" -v
