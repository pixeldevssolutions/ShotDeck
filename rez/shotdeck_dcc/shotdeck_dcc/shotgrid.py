"""Registering a published scene back in ShotGrid, from inside the DCC.

Deliberately narrow. ShotDeck's own publish dialog owns media publishing --
preflight, media inspection, upload retries, notes. What the DCC side owes is
the other half: the scene file an artist just published exists on disk, and
ShotGrid should know where it is.

So this creates a PublishedFile and nothing else. Field names mirror
config.PUBLISHED_FILE_* in the app, including the fallback when the site has
no LocalStorage covering the path -- a PublishedFile carrying the path as text
still beats no record at all.

Everything here degrades: no shotgun_api3, no key, or a site that refuses the
create leaves the file published on disk and says so. A registration failure
must never look like a failed publish, because the scene is already written.
"""

import os
import sys

from . import context

# The API key reaches the DCC because launcher.py builds the environment from
# os.environ, which already carries it. It is not exported by context.py and
# must not be -- see the note in publish.py.
KEY_VAR = "SG_SCRIPT_KEY"
SCRIPT_VAR = "SG_SCRIPT_NAME"
DEFAULT_SCRIPT = "SG_daemon"

# Extension -> PublishedFileType, matching config.PUBLISHED_FILE_TYPES. A type
# the site does not have is skipped rather than created.
FILE_TYPES = {
    ".ma": "Maya Scene",
    ".mb": "Maya Scene",
    ".nk": "Nuke Script",
    ".nknc": "Nuke Script",
    ".sfx": "Silhouette Project",
    ".hip": "Houdini Scene",
    ".hipnc": "Houdini Scene",
    ".hiplc": "Houdini Scene",
    ".blend": "Blender Scene",
    ".3de": "3DEqualizer Scene",
    ".spp": "Substance Painter Project",
    ".3dm": "Rhino Model",
    ".psd": "Photoshop Document",
    ".aep": "After Effects Project",
    ".zpr": "ZBrush Project",
}


class NotConfigured(RuntimeError):
    """No usable ShotGrid connection. The publish itself still succeeded."""


API_PATH_VAR = "SHOTDECK_SG_API_PATH"


def api():
    """The shotgun_api3 module, or None.

    A DCC ships its own Python and cannot see ShotDeck's venv, so the API is
    normally missing here. ShotDeck exports SHOTDECK_SG_API_PATH pointing at
    the directory it imports shotgun_api3 from; that is *appended* to sys.path
    -- never prepended -- so a venv full of PySide and other libraries can
    never shadow the DCC's own modules, which is how Qt collisions and hard
    crashes start.
    """
    try:
        import shotgun_api3
        return shotgun_api3
    except ImportError:
        pass

    path = os.environ.get(API_PATH_VAR)
    if not path or not os.path.isdir(path):
        return None
    if path not in sys.path:
        sys.path.append(path)
    try:
        import shotgun_api3
        return shotgun_api3
    except ImportError:
        return None


def available():
    """True when a registration attempt is worth making."""
    if api() is None:
        return False
    ctx = context.get()
    return bool(os.environ.get(KEY_VAR) and ctx.site and ctx.task_id)


def connect():
    """A ShotGrid connection for this DCC session."""
    shotgun_api3 = api()
    if shotgun_api3 is None:
        raise NotConfigured(
            "shotgun_api3 is not importable inside this DCC, so the publish "
            "was not registered in ShotGrid. {0} is {1} -- it is exported by "
            "ShotDeck at launch, so this session was either started outside "
            "ShotDeck or predates that export.".format(
                API_PATH_VAR,
                "unset" if not os.environ.get(API_PATH_VAR)
                else "set to " + os.environ[API_PATH_VAR]))

    ctx = context.get()
    key = os.environ.get(KEY_VAR)
    if not key:
        raise NotConfigured(
            "{0} is not set in this session, so the publish was not "
            "registered in ShotGrid.".format(KEY_VAR))
    if not ctx.site:
        raise NotConfigured("SHOTDECK_SITE is not set, so there is no site to "
                            "register the publish with.")

    return shotgun_api3.Shotgun(
        ctx.site,
        script_name=os.environ.get(SCRIPT_VAR) or DEFAULT_SCRIPT,
        api_key=key,
    )


def register(path, ctx=None, description="", sg=None):
    """Create a PublishedFile for `path`. Returns the created entity.

    Raises NotConfigured when ShotGrid is unreachable from this DCC; every
    other failure raises whatever shotgun_api3 raised, so the caller can put
    the real reason in front of the artist.
    """
    ctx = ctx or context.get()
    if not ctx.task_id:
        raise NotConfigured("This session has no task, so there is nothing to "
                            "register the publish against.")

    sg = sg or connect()
    data = {
        "project": {"type": "Project", "id": ctx.project_id},
        "code": os.path.basename(path),
        "task": {"type": "Task", "id": ctx.task_id},
        "path": {"local_path": path},
    }
    if ctx.entity_type and ctx.entity_id:
        data["entity"] = {"type": ctx.entity_type, "id": ctx.entity_id}
    if description:
        data["description"] = description

    file_type = _file_type(sg, path)
    if file_type:
        data["published_file_type"] = file_type

    try:
        return sg.create("PublishedFile", data)
    except Exception:
        # A local_path link only resolves when a LocalStorage covers the path.
        # Without one the site rejects the whole create, so fall back to the
        # path as text rather than losing the record.
        data.pop("path", None)
        data["description"] = (description + "\n" if description else "") + \
            "Published file: {0}".format(path)
        return sg.create("PublishedFile", data)


def _file_type(sg, path):
    name = FILE_TYPES.get(os.path.splitext(path)[1].lower())
    if not name:
        return None
    try:
        return sg.find_one("PublishedFileType", [["code", "is", name]],
                           ["code"])
    except Exception:
        return None            # an unknown type is not worth failing over
