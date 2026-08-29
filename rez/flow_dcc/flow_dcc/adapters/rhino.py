"""Rhino adapter.

Rhino's menus live in a .rui workspace file that is edited in the UI and
loaded per user; there is no supported way to add one from Python, and writing
into someone's .rui at startup is not a trade worth making for a menu. So
install() reports rather than pretends, and the actions are run from the
Python editor or bound to aliases -- see startup/rhino/README.txt.

Everything below the menu is the same pipeline as every other host: the same
names, the same versions, the same publish.
"""

import sys

from . import MENU_NAME, common


def _rhino():
    """RhinoCommon, which owns the document. Rhino-only import."""
    import Rhino
    return Rhino


def _rs():
    import rhinoscriptsyntax as rs
    return rs


def _doc():
    doc = _rhino().RhinoDoc.ActiveDoc
    if doc is None:
        raise RuntimeError("No open Rhino document.")
    return doc


def install():
    """No menu API in Rhino; say so once instead of failing silently."""
    from .. import log
    log.warning(
        "Rhino builds its menus from a .rui workspace, not from Python, so no "
        "%s menu was added. Run the actions from the Python editor: "
        "import flow_dcc; flow_dcc.adapter().action_version_up() -- "
        "or bind them to aliases, see startup/rhino/README.txt.", MENU_NAME)
    return False


def save_scene(path):
    """SaveAs reports success as a bool, not an exception."""
    if not _doc().SaveAs(path):
        raise RuntimeError("Rhino refused to save {0}".format(path))
    return path


def current_scene():
    return _doc().Path or ""


def message(text):
    sys.stdout.write("Flow: {0}\n".format(text))
    _rs().MessageBox(text, 0, "Flow")


def confirm(text):
    """MessageBox(..., 1) is OK/Cancel and returns 1 for OK."""
    return _rs().MessageBox(text, 1, "Flow") == 1


def ask_path(start_dir, extension, suggested=""):
    chosen = _rs().SaveFileName(
        "Flow: Save As",
        "Rhino Models (*{0})|*{0}||".format(extension or ".3dm"),
        start_dir, suggested)
    return chosen or None


# -- menu actions ---------------------------------------------------------

common.bind(sys.modules[__name__])
