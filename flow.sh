#!/usr/bin/env bash
# Launch Flow from a Linux command line.
#
#   /software/pipeline/Flow/flow.sh            # start it
#   /software/pipeline/Flow/flow.sh -v         # verbose log
#   FLOW_VENV=/opt/flow/venv ./flow.sh    # non-default venv
#
# To put it on everyone's PATH, once, as root:
#   ln -sf /software/pipeline/Flow/flow.sh /usr/local/bin/flow
#
# The symlink is resolved below, so `flow` from anywhere behaves the same
# as running this file in place.
#
# rez: set FLOW_REZ_REQUEST to the packages that provide the interpreter
# and Qt, and Flow runs inside that resolve instead of a venv:
#
#   FLOW_REZ_REQUEST="python-3.11 PySide6" flow
#
# Site-wide, put that line in /etc/sgdesk/sgdesk.env and nobody types it.
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
[ -f "$APP_ROOT/main.py" ] || { echo "Flow: no application at $APP_ROOT/main.py" >&2; exit 1; }

# ShotGrid credentials, root-owned, one file per workstation (DEPLOY-ROCKY9 §5).
# Sourced before the rez branch so the request itself can be set there.
set -a
[ -r /etc/sgdesk/sgdesk.env ] && . /etc/sgdesk/sgdesk.env
set +a

# PySide6 renders the tiles wrong under Rocky 9's wayland session.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

cd "$APP_ROOT"

# -- rez ---------------------------------------------------------------------
# The DCC launches already go through rez (config.REZ_EXECUTABLE); this puts
# Flow itself in the same boat, so one package set feeds the app and the
# DCCs it starts. Unset, nothing here runs and the venv path below is used.
if [ -n "${FLOW_REZ_REQUEST:-}" ]; then
    REZ="${FLOW_REZ_EXECUTABLE:-rez}"
    command -v "$REZ" >/dev/null || { echo "Flow: $REZ not on PATH -- set FLOW_REZ_EXECUTABLE." >&2; exit 1; }
    # Deliberately unquoted: the request is a package list, not one package.
    read -r -a REZ_PKGS <<<"$FLOW_REZ_REQUEST"
    [ -n "${FLOW_DRYRUN:-}" ] && exec "$REZ" env "${REZ_PKGS[@]}" -- python -c \
        'import sys, PySide6; print("python:", sys.executable); print("PySide6:", PySide6.__version__)'
    exec "$REZ" env "${REZ_PKGS[@]}" -- python main.py "$@"
fi

# -- venv --------------------------------------------------------------------
# First interpreter that exists wins. FLOW_VENV overrides for a venv kept
# off the app root (NFS start-up, see DEPLOY-ROCKY9 §"venv").
for candidate in \
    "${FLOW_VENV:-}/bin/python" \
    "$APP_ROOT/flow_venv/bin/python" \
    "$APP_ROOT/venv/bin/python" \
    "$APP_ROOT/../venv/bin/python"
do
    [ -x "$candidate" ] && PYTHON="$candidate" && break
done
PYTHON="${PYTHON:-$(command -v python3.11 || command -v python3 || true)}"

[ -n "$PYTHON" ] && [ -x "$PYTHON" ] || {
    echo "Flow: no Python found. Build the venv (DEPLOY-ROCKY9), set FLOW_VENV, or set FLOW_REZ_REQUEST." >&2
    exit 1
}

# Self-check: prove the interpreter resolved without starting a GUI.
[ -n "${FLOW_DRYRUN:-}" ] && { echo "python: $PYTHON"; echo "root  : $APP_ROOT"; exit 0; }

# Flat imports: config, paths and ui are top-level modules in the app root.
exec "$PYTHON" main.py "$@"
