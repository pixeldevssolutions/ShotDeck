#!/usr/bin/env bash
# Put the ShotDeck icon on this artist's desktop and in the applications menu.
#
# Per user, no root: everything it touches is under $HOME. Run it once per
# workstation login. Re-running is safe -- it overwrites its own copies and
# nothing else.
set -euo pipefail

APP_ROOT=/software/pipeline/ShotDeck
LAUNCHER="$APP_ROOT/launch_shotdeck.sh"
ICON="$APP_ROOT/shotdeck.png"
SOURCE_ENTRY="$APP_ROOT/ShotDeck.desktop"

MENU_DIR="$HOME/.local/share/applications"
MENU_ENTRY="$MENU_DIR/ShotDeck.desktop"

# xdg-user-dir knows the localised name; plain ~/Desktop is the fallback.
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -d "${DESKTOP_DIR:-}" ] || DESKTOP_DIR="$HOME/Desktop"
DESKTOP_ENTRY="$DESKTOP_DIR/ShotDeck.desktop"

[ -f "$SOURCE_ENTRY" ] || { echo "missing $SOURCE_ENTRY" >&2; exit 1; }
[ -x "$LAUNCHER" ] || chmod 0755 "$LAUNCHER"

if [ ! -f "$ICON" ]; then
    echo "note: no icon at $ICON -- falling back to the bundled logo" >&2
    ICON="$APP_ROOT/media/5and8_logo.png"
fi

install -d -m 0755 "$MENU_DIR" "$DESKTOP_DIR"

# One source of truth for the entry; only the icon line is rewritten, and only
# when the fallback kicked in.
sed "s|^Icon=.*|Icon=$ICON|" "$SOURCE_ENTRY" > "$MENU_ENTRY"
chmod 0644 "$MENU_ENTRY"

# The desktop copy must be executable, or GNOME and KDE both refuse to run it.
cp "$MENU_ENTRY" "$DESKTOP_ENTRY"
chmod 0755 "$DESKTOP_ENTRY"

# GNOME/Nautilus additionally wants the file marked trusted, or it shows
# "Untrusted application launcher" on the first double-click. KDE and XFCE go
# by the executable bit alone, so this is a no-op there.
gio set "$DESKTOP_ENTRY" metadata::trusted true 2>/dev/null || true
# Nautilus only re-reads the flag when the mtime moves.
touch "$DESKTOP_ENTRY"

command -v update-desktop-database >/dev/null && \
    update-desktop-database "$MENU_DIR" || true

echo "desktop icon : $DESKTOP_ENTRY"
echo "menu entry   : $MENU_ENTRY"
echo "launcher     : $LAUNCHER"
echo "icon         : $ICON"

# Fail here rather than on the artist's first double-click.
if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$MENU_ENTRY" && echo "desktop entry validates"
fi
