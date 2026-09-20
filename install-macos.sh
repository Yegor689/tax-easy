#!/usr/bin/env bash
# Sets up a venv with all dependencies needed to run TaxEasy on macOS.
#
# wxPython ships prebuilt wheels for macOS on PyPI, so unlike Ubuntu there's
# no system-dependency dance needed here -- just a venv and pip install.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if [[ "$(uname)" != "Darwin" ]]; then
    echo "This doesn't look like macOS -- see README.md's Setup section, or use" >&2
    echo "install-ubuntu.sh if you're on Ubuntu." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found. Install it first, e.g.:" >&2
    echo "  brew install python3" >&2
    echo "or from https://www.python.org/downloads/macos/" >&2
    exit 1
fi

required_major=3
required_minor=10
py_version="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
py_major="${py_version%%.*}"
py_minor="${py_version##*.}"
if (( py_major < required_major || (py_major == required_major && py_minor < required_minor) )); then
    echo "python3 is $py_version, but TaxEasy needs Python >= ${required_major}.${required_minor}." >&2
    echo "Install a newer Python, e.g.: brew install python3" >&2
    exit 1
fi

if [[ ! -d .venv ]]; then
    echo "Creating virtualenv (Python $py_version)..."
    python3 -m venv .venv
fi

echo "Installing TaxEasy and dependencies (wxPython's prebuilt macOS wheel, no compiling needed)..."
.venv/bin/pip install -e ".[dev]"

echo
echo "Done. Run the app with ./run.sh"
