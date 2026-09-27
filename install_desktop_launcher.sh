#!/usr/bin/env bash
# Install (or repair) the Flow desktop launcher, then start Flow.
#
#   cd /software/pipeline/Flow && ./install_desktop_launcher.sh
#
# Everything it writes is rewritten from the content below on every run, so
# running it twice leaves the same two .desktop files with the same bytes and
# the same modes -- no duplicates, no .bak copies. Nothing outside $HOME is
# touched; the launcher itself is flow.sh, which ships with the app.
set -euo pipefail

# The directory this script lives in: /software/pipeline/Flow on the farm.
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
MAIN="$APP_ROOT/main.py"
ICON="$APP_ROOT/media/5and8_logo.png"
# One launcher for both the icon and the command line -- flow.sh finds the
# interpreter, loads the credentials and starts the app.
LAUNCHER="$APP_ROOT/flow.sh"

MENU_DIR="$HOME/.local/share/applications"
MENU_ENTRY="$MENU_DIR/Flow.desktop"

# xdg-user-dir knows the localised name; plain ~/Desktop is the fallback.
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -d "${DESKTOP_DIR:-}" ] || DESKTOP_DIR="$HOME/Desktop"
DESKTOP_ENTRY="$DESKTOP_DIR/Flow.desktop"

die() { echo "Flow install: $*" >&2; exit 1; }

# -- 1. what must already be there -------------------------------------------
# Checked before anything is written, so a bad install leaves nothing behind.
[ -x "$LAUNCHER" ] || die "no launcher at $LAUNCHER"
[ -f "$MAIN" ]     || die "no application at $MAIN"
[ -f "$ICON" ]     || die "no icon at $ICON"

# Fails here rather than silently on the artist's first double-click.
FLOW_DRYRUN=1 "$LAUNCHER" >/dev/null || die "$LAUNCHER cannot find a Python interpreter"

# -- 2. the desktop entry, one copy on the desktop and one in the menu --------
install -d -m 0755 "$MENU_DIR" "$DESKTOP_DIR"

cat > "$MENU_ENTRY" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Flow
Comment=Flow Pipeline
Exec=$LAUNCHER
Icon=$ICON
Path=$APP_ROOT
Terminal=false
Categories=Graphics;Development;
StartupNotify=true
EOF
chmod 0755 "$MENU_ENTRY"

cp "$MENU_ENTRY" "$DESKTOP_ENTRY"
chmod 0755 "$DESKTOP_ENTRY"

# GNOME shows "Untrusted application launcher" on the first double-click until
# the file is both executable and flagged; KDE and XFCE go by the mode alone.
if command -v gio >/dev/null; then
    gio set "$DESKTOP_ENTRY" metadata::trusted true 2>/dev/null || true
fi
# Nautilus only re-reads the flag when the mtime moves.
touch "$DESKTOP_ENTRY"

command -v update-desktop-database >/dev/null && \
    update-desktop-database "$MENU_DIR" 2>/dev/null || true

echo "launcher   : $LAUNCHER"
echo "desktop    : $DESKTOP_ENTRY"
echo "menu entry : $MENU_ENTRY"
echo "icon       : $ICON"

# -- 3. only now, start it ---------------------------------------------------
# exec, so Flow replaces this shell: one process, and the exit status the
# artist sees is the app's own.
echo "starting Flow"
exec "$LAUNCHER"
