#!/usr/bin/env bash
# Sets up a venv with all dependencies needed to run TaxEasy on Ubuntu.
#
# wxPython has no prebuilt wheel on PyPI for Linux, so a plain `pip
# install` falls back to compiling wxWidgets from source -- slow, and it
# needs GTK3 dev headers most machines don't have. This script tries the
# fast path first (a prebuilt wheel from wxPython's own package index for
# your detected Ubuntu release) and only falls back to installing build
# dependencies and compiling from source if no matching wheel exists.
# See README.md's Setup section for the manual/non-scripted version of
# these same steps.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found -- install it first: sudo apt install python3 python3-venv" >&2
    exit 1
fi

if [[ ! -f /etc/os-release ]]; then
    echo "This doesn't look like Ubuntu (/etc/os-release missing) -- this script is Ubuntu-specific." >&2
    echo "See README.md's Setup section for other platforms." >&2
    exit 1
fi

# shellcheck source=/dev/null
source /etc/os-release
ubuntu_release="${VERSION_ID:-}"
if [[ -z "$ubuntu_release" ]]; then
    echo "Couldn't detect your Ubuntu version from /etc/os-release." >&2
    exit 1
fi

echo "Detected Ubuntu $ubuntu_release."

if [[ ! -d .venv ]]; then
    echo "Creating virtualenv..."
    python3 -m venv .venv
fi

venv_pip="$script_dir/.venv/bin/pip"

install_prebuilt_wheel() {
    local wheel_url="https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-${ubuntu_release}"
    echo "Trying a prebuilt wxPython wheel for ubuntu-${ubuntu_release}..."
    # --no-index restricts pip to this URL alone -- without it, pip also
    # checks PyPI and picks the *highest version overall*, which for Linux
    # is always a source-only release with no wheel, silently falling back
    # to compiling anyway (-f/--find-links supplements the default index,
    # it doesn't replace it). See README.md for the full explanation.
    "$venv_pip" install --no-index -f "$wheel_url" wxPython
}

install_from_source() {
    echo "No prebuilt wheel available for ubuntu-${ubuntu_release} -- installing build"
    echo "dependencies and compiling wxPython from source instead. This is slow"
    echo "(15-30+ minutes) and needs sudo to install system packages."
    sudo apt-get update
    sudo apt-get install -y build-essential pkg-config libgtk-3-dev libnotify-dev \
        libsdl2-dev libjpeg-dev libtiff-dev libsm-dev libwebkit2gtk-4.1-dev \
        libgstreamer-plugins-base1.0-dev freeglut3-dev libgl1-mesa-dev libglu1-mesa-dev
    "$venv_pip" install wxPython
}

if ! "$venv_pip" show wxPython >/dev/null 2>&1; then
    if ! install_prebuilt_wheel; then
        install_from_source
    fi
else
    echo "wxPython already installed in .venv, skipping."
fi

# wx.html2.WebView (the Calculation Detail tab) needs WebKitGTK at runtime
# regardless of how wxPython itself was installed above.
if ! dpkg -s libwebkit2gtk-4.1-0 >/dev/null 2>&1 && ! dpkg -s libwebkit2gtk-4.0-37 >/dev/null 2>&1; then
    echo "Installing libwebkit2gtk (needed at runtime for the Calculation Detail view)..."
    # apt-get update here too, in case install_from_source's update above
    # didn't run (prebuilt-wheel path) and this is a fresh/stale apt cache.
    sudo apt-get update
    sudo apt-get install -y libwebkit2gtk-4.1-0 || sudo apt-get install -y libwebkit2gtk-4.0-37
fi

echo "Installing TaxEasy and remaining dependencies..."
"$venv_pip" install -e ".[dev]"

echo
echo "Done. Run the app with ./run.sh"
