#!/usr/bin/env bash
# Launches TaxEasy from its virtualenv, regardless of the working
# directory this script is run from (e.g. double-clicked in Finder or
# a file manager, which starts with an unpredictable cwd).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv_bin="$script_dir/.venv/bin"

if [[ ! -x "$venv_bin/tax-easy" ]]; then
    echo "No virtualenv found at $script_dir/.venv -- set it up first:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -e ." >&2
    exit 1
fi

exec "$venv_bin/tax-easy"
