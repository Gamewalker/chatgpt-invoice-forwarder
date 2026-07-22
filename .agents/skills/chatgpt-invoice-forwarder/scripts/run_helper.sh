#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../../../.." && pwd)
venv_python="$repo_root/.venv/bin/python"

if [ ! -x "$venv_python" ]; then
    echo "Lokale Python-Umgebung fehlt. Führe zuerst scripts/setup.sh aus." >&2
    exit 3
fi

exec "$venv_python" -m chatgpt_invoice_agent --config "$repo_root/config/agent.json" "$@"
