"""Where this task's scenes live, from inside the DCC.

The entity root (/jobs/UAT6/sequences/SEQ001/shots/AD1030) is not re-derived
here: ShotDeck already built it from config.ENTITY_PATH_TEMPLATES and exports
it as SHOTDECK_ENTITY_ROOT. Duplicating the templates in a package that ships
separately is how the two drift apart.

Only the leaf -- which subfolder and which file extension a given DCC uses --
is decided here, and it matches config.ENTITY_SUBFOLDERS in the app.
"""

import os
import re

from . import context

# software code -> (subfolder under the entity root, scene extension).
# {step} is the pipeline step lowercased; it collapses out when the launch had
# no step, so a task without one still saves somewhere sensible.
LAYOUT = {
    "maya": ("maya/scenes/{step}", ".ma"),
    "nuke": ("nuke/{step}/scene", ".nk"),
    "silhouette": ("silhouette/{step}/scene", ".sfx"),
    "houdini": ("houdini/hip/{step}", ".hip"),
    "blender": ("blender/scenes/{step}", ".blend"),
}
DEFAULT_LAYOUT = ("{software}/{step}/scene", "")

# Where a published scene lands, per DCC. Publishes sit beside the work
# folder rather than inside it, so "everything under publish/ is safe to
# reference" stays true no matter what an artist saves next door.
PUBLISH_LAYOUT = {
    "maya": "maya/publish/{step}",
    "nuke": "nuke/{step}/publish",
    "silhouette": "silhouette/{step}/publish",
    "houdini": "houdini/publish/{step}",
    "blender": "blender/publish/{step}",
}
DEFAULT_PUBLISH_LAYOUT = "{software}/{step}/publish"

VERSION_RE = re.compile(r"_v(\d+)", re.IGNORECASE)


def _layout(software):
    return LAYOUT.get((software or "").lower(), DEFAULT_LAYOUT)


def work_dir(ctx=None):
    """Folder this DCC's scenes belong in. None when the launch had no entity.

    None is a real answer -- ShotDeck allows launching with no task selected,
    and the caller has to say "pick a task and relaunch" rather than invent a
    path in the artist's home directory.
    """
    ctx = ctx or context.get()
    root = (ctx.entity_root or "").rstrip("/")
    if not root:
        return None

    template, _ = _layout(ctx.software)
    relative = template.format(step=(ctx.step or "").lower(),
                               software=(ctx.software or "dcc").lower())
    # Collapse the empty {step} rather than leaving a // in the path.
    parts = [p for p in relative.split("/") if p]
    return "/".join([root] + parts)


def publish_dir(ctx=None):
    """Folder published scenes belong in. None when the launch had no entity."""
    ctx = ctx or context.get()
    root = (ctx.entity_root or "").rstrip("/")
    if not root:
        return None

    template = PUBLISH_LAYOUT.get((ctx.software or "").lower(),
                                  DEFAULT_PUBLISH_LAYOUT)
    relative = template.format(step=(ctx.step or "").lower(),
                               software=(ctx.software or "dcc").lower())
    parts = [p for p in relative.split("/") if p]
    return "/".join([root] + parts)


def publish_path(version, ctx=None, ext=None):
    """Absolute path a published version lands at, or None without a task.

    Same file name as the work file it came from: the version number is the
    link between the two, and renaming on publish only makes them hard to
    match up later.
    """
    folder = publish_dir(ctx)
    if not folder:
        return None
    return folder + "/" + scene_name(version, ctx, ext)


def extension(ctx=None):
    ctx = ctx or context.get()
    _, ext = _layout(ctx.software)
    return ext


def scene_stem(ctx=None):
    """`AD1030_comp` -- entity and step, the studio's existing file convention."""
    ctx = ctx or context.get()
    bits = [b for b in (ctx.entity_name, (ctx.step or "").lower()) if b]
    return "_".join(bits) or "untitled"


def scene_name(version, ctx=None, ext=None):
    """`AD1030_comp_v003.ma`."""
    ctx = ctx or context.get()
    if ext is None:
        ext = extension(ctx)
    return "{0}_v{1:03d}{2}".format(scene_stem(ctx), int(version), ext)


def scene_path(version, ctx=None, ext=None):
    """Absolute path for a version, or None when there is no work folder."""
    folder = work_dir(ctx)
    if not folder:
        return None
    return folder + "/" + scene_name(version, ctx, ext)


def existing_versions(ctx=None, ext=None):
    """Version numbers already on disk for this task, ascending.

    Matches on the stem so an unrelated scene in a shared folder is not counted
    as a previous version of this task's work.
    """
    folder = work_dir(ctx)
    if not folder or not os.path.isdir(folder):
        return []

    ctx = ctx or context.get()
    if ext is None:
        ext = extension(ctx)
    stem = scene_stem(ctx).lower()

    found = []
    for name in os.listdir(folder):
        lowered = name.lower()
        if not lowered.startswith(stem + "_v"):
            continue
        if ext and not lowered.endswith(ext.lower()):
            continue
        match = VERSION_RE.search(lowered)
        if match:
            found.append(int(match.group(1)))
    return sorted(set(found))
