"""Nuke adapter: the ShotDeck menu on Nuke's menu bar.

The `nuke` module is imported inside the functions so this file can be read,
imported and tested outside Nuke.
"""

import sys

from . import ACTIONS, MENU_NAME, common


def _nuke():
    import nuke
    return nuke


def install():
    """Add the ShotDeck menu. No-op in a terminal session, which has no menus."""
    nuke = _nuke()
    if nuke.env.get("gui") is False:
        return False

    menu = nuke.menu("Nuke").addMenu(MENU_NAME)
    module = sys.modules[__name__]
    for label, attr in ACTIONS:
        if label is None:
            menu.addSeparator()
            continue
        menu.addCommand(label, getattr(module, attr))
    return True


def save_scene(path):
    _nuke().scriptSaveAs(path, overwrite=1)
    return path


def current_scene():
    return _nuke().root().name() or ""


def message(text):
    """nuke.message is modal; the terminal gets a copy for the launch log."""
    sys.stdout.write("ShotDeck: {0}\n".format(text))
    _nuke().message(text)


# -- menu actions ---------------------------------------------------------

def action_save_next_version():
    return common.save_next_version(sys.modules[__name__])


def action_open_work_folder():
    return common.open_work_folder(sys.modules[__name__])


def action_show_context():
    return common.show_context(sys.modules[__name__])
