"""3DEqualizer adapter.

3DE has no runtime menu API at all: it builds its menus once at startup by
reading the header comments of every script in 3DE4_PYTHON_CUSTOM_SCRIPTS_DIR.
The ShotDeck menu therefore ships as those scripts (startup/3de/), and each of
them calls one action here. install() has no menu to build, so it checks that
3DE can actually see the scripts instead -- a deploy that missed the
environment variable shows up as a line in the log rather than as a menu
nobody can find.

`tde4` is a built-in module inside 3DE only, so it is imported per call.
"""

import os
import sys

from . import MENU_NAME, common

SCRIPTS_VAR = "3DE4_PYTHON_CUSTOM_SCRIPTS_DIR"


def _tde4():
    import tde4
    return tde4


def install():
    """Confirm 3DE is reading the shipped scripts. Nothing to build here."""
    from .. import log

    root = os.environ.get("SHOTDECK_DCC_ROOT", "")
    ours = os.path.join(root, "startup", "3de") if root else ""
    listed = [p for p in os.environ.get(SCRIPTS_VAR, "").split(os.pathsep) if p]

    if ours and os.path.normpath(ours) in [os.path.normpath(p) for p in listed]:
        return True

    log.warning(
        "%s is not on %s, so the %s menu will not appear. Resolve the "
        "shotdeck_dcc rez package, or run the actions from 3DE's Python "
        "console: import shotdeck_dcc; shotdeck_dcc.adapter().action_save()",
        ours or "startup/3de", SCRIPTS_VAR, MENU_NAME)
    return False


def save_scene(path):
    """tde4.saveProject reports success as a return code, not an exception."""
    if not _tde4().saveProject(path):
        raise RuntimeError("3DEqualizer refused to save {0}".format(path))
    return path


def current_scene():
    return _tde4().getProjectPath() or ""


def message(text):
    tde4 = _tde4()
    sys.stdout.write("ShotDeck: {0}\n".format(text))
    tde4.postQuestionRequester("ShotDeck", text, "OK")


def confirm(text):
    """postQuestionRequester returns the 1-based index of the button pressed."""
    return _tde4().postQuestionRequester(
        "ShotDeck", text, "Publish", "Cancel") == 1


def ask_path(start_dir, extension, suggested=""):
    """3DE's file requester takes a pattern; a full path pre-fills the name."""
    pattern = (os.path.join(start_dir, suggested) if suggested
               else "*{0}".format(extension or ""))
    return _tde4().postFileRequester("ShotDeck: Save As", pattern) or None


# -- menu actions ---------------------------------------------------------

common.bind(sys.modules[__name__])
