#!/usr/bin/env bash
# Build the standalone ShotDeck binary. Run this ON ROCKY 9 -- PyInstaller does
# not cross-compile, so a Windows build produces a Windows exe and nothing else.
#
#   cd /software/pipeline/ShotDeck && ./tools/build/build_rocky9.sh
#   SHOTDECK_BUILD_PYTHON=/opt/python3.11/bin/python3 ./tools/build/build_rocky9.sh
#
# Output:
#   dist/ShotDeck/ShotDeck          the binary
#   dist/ShotDeck-<ver>-el9.tar.gz  the same folder, ready to copy to a farm box
#
# The build venv lives in build/venv and is reused; delete it to start clean.
# Qt needs these on the build box and on every box that runs the result:
#   sudo dnf install -y libxkbcommon-x11 xcb-util-cursor xcb-util-wm \
#        xcb-util-keysyms xcb-util-image xcb-util-renderutil \
#        libxkbcommon fontconfig mesa-libGL
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
cd "$APP_ROOT"

[ "$(uname -s)" = "Linux" ] || {
    echo "build: this produces an el9 binary and must run on Rocky 9, not $(uname -s)." >&2
    exit 1
}
[ -f main.py ] || { echo "build: no application at $APP_ROOT/main.py" >&2; exit 1; }

# 3.11 first: PySide6 wheels for it are current, and Rocky 9's stock 3.9 is not.
PYTHON="${SHOTDECK_BUILD_PYTHON:-$(command -v python3.11 || command -v python3.12 || command -v python3)}"
[ -n "$PYTHON" ] && [ -x "$PYTHON" ] || {
    echo "build: no Python found -- dnf install python3.11, or set SHOTDECK_BUILD_PYTHON." >&2
    exit 1
}
echo "python : $PYTHON ($("$PYTHON" -V))"

VENV="$APP_ROOT/build/venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo "creating build venv at $VENV"
    "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r requirements.txt pyinstaller

# --clean, so a stale Analysis cache never silently ships an old module.
"$VENV/bin/python" -m PyInstaller --clean --noconfirm \
    --distpath dist --workpath build/pyinstaller \
    tools/build/shotdeck.spec

BIN="$APP_ROOT/dist/ShotDeck/ShotDeck"
[ -x "$BIN" ] || { echo "build: PyInstaller reported success but $BIN is missing." >&2; exit 1; }

# Smoke test: argparse exits before QApplication, so this proves the bundle
# imports and starts without needing a display on the build box.
"$BIN" --help >/dev/null || { echo "build: $BIN cannot start -- see the traceback above." >&2; exit 1; }

VERSION="$(git -C "$APP_ROOT" describe --tags --always --dirty 2>/dev/null || date +%Y%m%d)"
TARBALL="$APP_ROOT/dist/ShotDeck-${VERSION}-el9.tar.gz"
tar -czf "$TARBALL" -C "$APP_ROOT/dist" ShotDeck

echo
echo "binary  : $BIN"
echo "tarball : $TARBALL"
echo
echo "Deploy: untar under /software/pipeline, then run ShotDeck/ShotDeck."
echo "Credentials still come from /etc/sgdesk/sgdesk.env (DEPLOY-ROCKY9 §5)."
