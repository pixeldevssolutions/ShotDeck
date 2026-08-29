"""Blender adapter: a 5and8 menu in the top bar.

Blender's UI is declarative: a menu entry has to be an Operator class and a
menu has to be a Menu class, both registered with bpy.utils. The classes are
therefore generated from ACTIONS at install time rather than written out by
hand, so the menu here stays the same menu as everywhere else.

Two things Blender genuinely cannot do are handled rather than faked:

  * its file browser is modal and returns through an operator, never to the
    caller, so Save As is handed to Blender's own save_as_mainfile with the
    pipeline name pre-filled instead of going through common.save_as();
  * it has no blocking confirm dialog callable from plain Python, so confirm()
    reports and proceeds -- see the note there.
"""

import os
import sys

from . import ACTIONS, MENU_NAME, common
from .. import paths, versioning

MENU_ID = "FLOW_MT_menu"

# Everything install() registered, so a second install() replaces the menu
# rather than stacking another one on top of it.
_registered = []


def _bpy():
    import bpy
    return bpy


def install():
    """Register an operator per action, a menu holding them, and show it."""
    bpy = _bpy()
    if bpy.app.background:
        return False                        # -b: no top bar to hang it on

    uninstall()
    module = sys.modules[__name__]
    entries = []
    for label, attr in ACTIONS:
        if label is None:
            entries.append(None)
            continue
        cls = _operator(bpy, module, label, attr)
        bpy.utils.register_class(cls)
        _registered.append(cls)
        entries.append(cls.bl_idname)

    def draw(self, _context):
        for idname in entries:
            if idname is None:
                self.layout.separator()
            else:
                self.layout.operator(idname)

    menu = type("FLOW_MT_menu", (bpy.types.Menu,), {
        "bl_idname": MENU_ID,
        "bl_label": MENU_NAME,
        "draw": draw,
    })
    bpy.utils.register_class(menu)
    _registered.append(menu)

    bpy.types.TOPBAR_MT_editor_menus.append(_draw_top_bar)
    return True


def uninstall():
    """Take the menu back off. Called by install() and by the add-on unload."""
    bpy = _bpy()
    try:
        bpy.types.TOPBAR_MT_editor_menus.remove(_draw_top_bar)
    except ValueError:
        pass                                # was never installed
    while _registered:
        try:
            bpy.utils.unregister_class(_registered.pop())
        except Exception:
            pass                            # already gone with the file load


def _draw_top_bar(self, _context):
    self.layout.menu(MENU_ID)


def _operator(bpy, module, label, attr):
    """One Operator class wrapping one action. Blender accepts nothing else."""

    def execute(self, _context):
        getattr(module, attr)()
        return {"FINISHED"}

    return type("FLOW_OT_" + attr, (bpy.types.Operator,), {
        "bl_idname": "flow." + attr,
        "bl_label": label,
        "bl_options": {"REGISTER"},
        "execute": execute,
    })


def save_scene(path):
    _bpy().ops.wm.save_as_mainfile(filepath=path)
    return path


def current_scene():
    return _bpy().data.filepath or ""


def message(text):
    """A popup in the UI, and the console either way for the launch log."""
    bpy = _bpy()
    sys.stdout.write("Flow: {0}\n".format(text))
    if bpy.app.background:
        return

    def draw(self, _context):
        for line in text.splitlines():
            self.layout.label(text=line)

    bpy.context.window_manager.popup_menu(draw, title="Flow", icon="INFO")


def confirm(text):
    """Report and proceed: Blender has no blocking confirm from plain Python.

    Its confirmation dialogs are operators that answer through a callback, so
    a function that must return True or False right now cannot use one.
    Publishing is still deliberate -- the artist clicked Publish... -- and it
    refuses on its own if the version already exists, so proceeding is safe in
    a way that silently skipping a real check would not be.
    """
    message(text)
    return True


def ask_path(start_dir, extension, suggested=""):
    """No synchronous file dialog exists; action_save_as() is used instead."""
    return None


# -- Deadline -------------------------------------------------------------

def frame_range():
    scene = getattr(_bpy().context, "scene", None)
    if scene is None:
        return None                         # no scene during a file load
    return int(scene.frame_start), int(scene.frame_end)


def deadline_plugin_info(scene):
    """Keys only Blender knows. OutputFile is the scene's own output path."""
    bpy = _bpy()
    return {
        "Version": "{0}.{1}".format(*bpy.app.version[:2]),
        "OutputFile": bpy.context.scene.render.filepath,
        "Threads": 0,                       # let the render node decide
        "Build": "None",                    # whichever Blender the pool has
    }


# -- menu actions ---------------------------------------------------------

def action_save_as():
    """Blender's own Save As, opened on the work folder, name pre-filled.

    common.save_as() cannot be used here: it needs the chosen path back, and
    Blender's file browser only ever reports to the operator it launched. The
    trade is that Flow does not get to comment on where the file landed --
    which Blender's own title bar shows anyway.
    """
    bpy = _bpy()
    start = paths.work_dir() or os.path.expanduser("~")
    try:
        suggested = os.path.basename(versioning.next_scene_path())
    except ValueError:
        suggested = ""                      # no task: Blender picks the name
    bpy.ops.wm.save_as_mainfile("INVOKE_DEFAULT",
                                filepath=os.path.join(start, suggested))
    return None


common.bind(sys.modules[__name__])
