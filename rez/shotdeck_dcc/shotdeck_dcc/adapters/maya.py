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


def confirm(text):
    """Yes/no before something that writes. Defaults to Cancel."""
    return _cmds().confirmDialog(
        title="ShotDeck", message=text, button=["Continue", "Cancel"],
        defaultButton="Cancel", cancelButton="Cancel",
        dismissString="Cancel") == "Continue"


def ask_path(start_dir, extension, suggested=""):
    """Save-file dialog, opened on the work folder with the name pre-filled.

    fileDialog2 has no separate default-name argument -- passing a full path
    as startingDirectory is what pre-fills the name field.
    """
    import os

    cmds = _cmds()
    file_filter = ("Maya Files (*.ma *.mb)" if extension in (".ma", ".mb")
                   else "All Files (*.*)")
    start = os.path.join(start_dir, suggested) if suggested else start_dir
    chosen = cmds.fileDialog2(fileMode=0, caption="ShotDeck: Save As",
                              startingDirectory=start,
                              fileFilter=file_filter)
    return chosen[0] if chosen else None


# -- Deadline -------------------------------------------------------------

def frame_range():
    """Maya's playback range, which is what its render globals render."""
    cmds = _cmds()
    return (int(cmds.playbackOptions(query=True, minTime=True)),
            int(cmds.playbackOptions(query=True, maxTime=True)))


def deadline_plugin_info(scene):
    """Keys only Maya knows. The frames and the scene are handled above it.

    ProjectPath matters more than it looks: a batch render resolves every
    relative texture and cache path against the workspace, so a job submitted
    without it renders grey.
    """
    cmds = _cmds()
    return {
        "Version": cmds.about(query=True, version=True).split()[0],
        "ProjectPath": cmds.workspace(query=True, rootDirectory=True),
        "Renderer": cmds.getAttr("defaultRenderGlobals.currentRenderer"),
        # A scene that errors should fail the task, not render 120 black
        # frames that someone reviews tomorrow.
        "StrictErrorChecking": True,
    }


# -- menu actions ---------------------------------------------------------

common.bind(sys.modules[__name__])
