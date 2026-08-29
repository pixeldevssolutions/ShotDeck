"""Houdini adapter: the Flow menu on Houdini's main menu bar.

Houdini has no runtime API for adding to its own menus -- the documented route
is a MainMenuCommon.xml scanned once at startup, which cannot be rebuilt while
Houdini is running and cannot call back into a module that was not on
PYTHONPATH when it was read. The menu is therefore added straight to the Qt
menu bar of the main window, which is the same bar the XML feeds.

`hou` is imported inside the functions so this module can be imported and
tested outside Houdini.
"""

import os
import sys

from . import ACTIONS, MENU_NAME, common

MENU_OBJECT = "flowMenu"


def _hou():
    import hou
    return hou


def install():
    """Build the menu, replacing any earlier one. No-op in hython/batch."""
    hou = _hou()
    if not hou.isUIAvailable():
        return False                       # hython, -b: there is no menu bar

    bar = hou.qt.mainWindow().menuBar()
    for action in bar.actions():
        menu = action.menu()
        if menu is not None and menu.objectName() == MENU_OBJECT:
            bar.removeAction(action)       # a second install(), not a second menu

    menu = bar.addMenu(MENU_NAME)
    menu.setObjectName(MENU_OBJECT)
    module = sys.modules[__name__]
    for label, attr in ACTIONS:
        if label is None:
            menu.addSeparator()
            continue
        menu.addAction(label, getattr(module, attr))
    return True


def save_scene(path):
    _hou().hipFile.save(file_name=path)
    return path


def current_scene():
    """The open .hip, or "" when Houdini is still on its untitled scene.

    hipFile.path() never returns empty -- an unsaved session reports
    $HOME/untitled.hip, which is not a file the pipeline should save over.
    """
    path = _hou().hipFile.path() or ""
    if os.path.basename(path).startswith("untitled."):
        return ""
    return path


def message(text):
    """A dialog in the UI, and the terminal either way for the launch log."""
    hou = _hou()
    sys.stdout.write("Flow: {0}\n".format(text))
    if hou.isUIAvailable():
        hou.ui.displayMessage(text, title="Flow")


def confirm(text):
    """Yes/no before something that writes. Defaults to Cancel."""
    hou = _hou()
    if not hou.isUIAvailable():
        return False                       # nobody is there to answer
    return hou.ui.displayMessage(text, buttons=("Continue", "Cancel"),
                                 default_choice=1, close_choice=1,
                                 title="Flow") == 0


def ask_path(start_dir, extension, suggested=""):
    """Save-file dialog, opened on the work folder with the name pre-filled."""
    hou = _hou()
    chosen = hou.ui.selectFile(
        start_directory=start_dir, title="Flow: Save As",
        collapse_sequences=False, pattern="*{0}".format(extension or ""),
        default_value=suggested, chooser_mode=hou.fileChooserMode.Write)
    if not chosen:
        return None
    # Houdini hands paths back with its own variables still in them ($HIP/...),
    # which the rest of the pipeline cannot resolve.
    return hou.text.expandString(chosen.strip())


# -- Deadline -------------------------------------------------------------

def frame_range():
    start, end = _hou().playbar.frameRange()
    return int(start), int(end)


def deadline_plugin_info(scene):
    """Keys only Houdini knows.

    Deadline's Houdini plugin renders one output driver, and a .hip commonly
    holds several. Guessing which is a render nobody asked for, so a ROP has
    to be selected -- and the refusal says that rather than submitting
    something plausible.
    """
    hou = _hou()
    rop = None
    for node in hou.selectedNodes():
        if isinstance(node, hou.RopNode):
            rop = node
            break

    if rop is None:
        from .. import deadline
        raise deadline.DeadlineError(
            "Select the ROP to render before submitting. Deadline renders one "
            "output driver per job, and this .hip may hold several -- "
            "Flow will not pick one for you.")

    return {
        "Version": ".".join(hou.applicationVersionString().split(".")[:2]),
        "OutputDriver": rop.path(),
        # The ROP's own inputs are its business; a farm job that re-cooks them
        # is how one submission becomes an hour of duplicated work.
        "IgnoreInputs": False,
    }


# -- menu actions ---------------------------------------------------------

common.bind(sys.modules[__name__])
