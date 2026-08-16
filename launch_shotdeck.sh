#!/usr/bin/env bash
# Start ShotDeck from a desktop icon, where there is no login shell.
#
# A double-click does not source ~/.bashrc or /etc/profile.d, so anything the
# app needs from the environment has to be set here or it comes up broken with
# no terminal to say why.
set -euo pipefail

APP_ROOT=/software/pipeline/ShotDeck
VENV="$APP_ROOT/shotdeck_venv"

# ShotGrid credentials, root-owned, one file per workstation (DEPLOY-ROCKY9 §5).
set -a
[ -r /etc/sgdesk/sgdesk.env ] && . /etc/sgdesk/sgdesk.env
set +a

# Qt picks wayland by default on Rocky 9's GNOME session and PySide6 renders
# the tiles wrong under it; xcb unless something already chose.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

# Flat imports: config, paths and ui are top-level modules in APP_ROOT.
cd "$APP_ROOT"

# A desktop launch has nowhere to print, so keep the first failure readable.
if [ ! -x "$VENV/bin/python" ]; then
    message="ShotDeck: no interpreter at $VENV/bin/python"
    command -v zenity >/dev/null && zenity --error --text="$message" || true
    echo "$message" >&2
    exit 1
fi

exec "$VENV/bin/python" "$APP_ROOT/main.py" "$@"
