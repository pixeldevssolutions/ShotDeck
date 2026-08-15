"""Maya adapter: the ShotDeck menu on Maya's main menu bar.

maya.cmds is imported inside the functions, not at module scope, so importing
this module outside Maya (a test, a lint pass) does not explode.
"""

import sys

from . import ACTIONS, MENU_NAME, common

MENU_OBJECT = "shotdeckMenu"


def _cmds():
    import maya.cmds as cmds
    return cmds


def install():
    """Build the menu, replacing any earlier one.

    Deferred by the startup hook rather than here: at the point userSetup.py
    runs, Maya's main window does not exist yet and menu(parent=...) fails.
    """
    cmds = _cmds()
    if cmds.about(batch=True):
        return False                       # mayapy / batch: no menu bar

    if cmds.menu(MENU_OBJECT, exists=True):
        cmds.deleteUI(MENU_OBJECT)

    import maya.mel as mel
    parent = mel.eval("$tmp = $gMainWindow")
    cmds.menu(MENU_OBJECT, label=MENU_NAME, parent=parent, tearOff=True)

    module = sys.modules[__name__]
    for label, attr in ACTIONS:
        if label is None:
            cmds.menuItem(divider=True)
            continue
        cmds.menuItem(label=label, command=_callback(getattr(module, attr)))
    return True


def _callback(func):
    """Maya passes the menu item's state as an argument; swallow it."""
    return lambda *_: func()


def save_scene(path):
    """Save the open scene to `path`, picking the type from the extension."""
    cmds = _cmds()
    file_type = "mayaAscii" if path.lower().endswith(".ma") else "mayaBinary"
    cmds.file(rename=path)
    cmds.file(save=True, type=file_type)
    return path


def current_scene():
    return _cmds().file(query=True, sceneName=True) or ""


def message(text):
    """Status line for one-liners, a dialog for anything multi-line."""
    cmds = _cmds()
    first = text.splitlines()[0] if text else ""
    cmds.inViewMessage(assistMessage=first, position="topCenter", fade=True)
    if "\n" in text:
        cmds.confirmDialog(title="ShotDeck", message=text, button=["Close"])


# -- menu actions ---------------------------------------------------------

def action_save_next_version():
    return common.save_next_version(sys.modules[__name__])


def action_open_work_folder():
    return common.open_work_folder(sys.modules[__name__])


def action_show_context():
    return common.show_context(sys.modules[__name__])
