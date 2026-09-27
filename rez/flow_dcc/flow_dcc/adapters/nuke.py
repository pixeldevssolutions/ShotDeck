"""Nuke adapter: the Flow menu on Nuke's menu bar.

The `nuke` module is imported inside the functions so this file can be read,
imported and tested outside Nuke.
"""

import sys

from . import MENU_NAME, actions, common


def _nuke():
    import nuke
    return nuke


def install():
    """Add the Flow menu. No-op in a terminal session, which has no menus."""
    nuke = _nuke()
    if nuke.env.get("gui") is False:
        return False

    menu = nuke.menu("Nuke").addMenu(MENU_NAME)
    module = sys.modules[__name__]
    for label, attr in actions(module):
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
    sys.stdout.write("Flow: {0}\n".format(text))
    _nuke().message(text)


def confirm(text):
    return bool(_nuke().ask(text))


def ask_path(start_dir, extension, suggested=""):
    chosen = _nuke().getFilename("Flow: Save As",
                                 "*{0}".format(extension or ""),
                                 default=start_dir + "/" + suggested)
    return chosen or None


# -- Deadline -------------------------------------------------------------

def frame_range():
    root = _nuke().root()
    return int(root.firstFrame()), int(root.lastFrame())


def deadline_plugin_info(scene):
    """Keys only Nuke knows.

    A selected Write node narrows the job to that one, which is what an artist
    means by selecting it. Nothing selected renders every Write, which is what
    Nuke itself does.
    """
    nuke = _nuke()
    info = {
        "Version": ".".join(nuke.NUKE_VERSION_STRING.split(".")[:2]),
        "BatchMode": True,
        "NukeX": bool(nuke.env.get("nukex")),
    }
    selected = [node.name() for node in nuke.selectedNodes("Write")]
    if selected:
        info["WriteNode"] = selected[0]
    return info


# -- USD (flow_dcc/usd.py) ------------------------------------------------

def export_usd(path, root_prim=None):
    """Write the selected 3D node's scene through a throwaway WriteGeo.

    For what Nuke contributes to a shot -- a solved or tracked camera, cards.
    `root_prim` is not applied: Nuke names prims after its nodes, and
    usd.check_layer refuses an asset layer that is not under /<asset>.
    """
    nuke = _nuke()
    source = nuke.selectedNodes()
    if not source:
        raise RuntimeError(
            "Select the 3D node to publish (a Camera or a Scene) and publish "
            "again.")
    write = nuke.nodes.WriteGeo(inputs=[source[0]])
    try:
        write["file"].setValue(path)
        write["file_type"].setValue("usd")
        first, last = frame_range()
        nuke.execute(write, first, last)
    finally:
        nuke.delete(write)
    return path


def load_usd_stage(path):
    """A ReadGeo on the stage, reused if one already reads it."""
    nuke = _nuke()
    for node in nuke.allNodes("ReadGeo2"):
        if node["file"].value() == path:
            return node
    node = nuke.nodes.ReadGeo2()
    node["file"].setValue(path)
    return node


# -- menu actions ---------------------------------------------------------

common.bind(sys.modules[__name__])
