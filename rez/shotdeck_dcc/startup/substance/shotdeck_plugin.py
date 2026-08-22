"""Substance 3D Painter plugin, reached through SUBSTANCE_PAINTER_PLUGINS_PATH.

Painter loads every plugin in that path and calls start_plugin() on load and
close_plugin() on unload -- the unload half matters here, because Painter
reloads plugins during a session and the File menu would otherwise collect a
second set of ShotDeck actions each time.
"""

import traceback


def start_plugin():
    try:
        import shotdeck_dcc
        shotdeck_dcc.install()
    except Exception:
        traceback.print_exc()


def close_plugin():
    try:
        from shotdeck_dcc.adapters import substance
        substance.uninstall()
    except Exception:
        traceback.print_exc()
