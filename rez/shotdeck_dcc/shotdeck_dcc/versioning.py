"""Which version number comes next.

Deliberately filesystem-based rather than ShotGrid-based: the DCC may be on a
box without shotgun_api3, and an artist saving a work file should never be
blocked by the site being slow or down. ShotGrid is the authority on published
Versions, not on work-in-progress scenes.
"""

import os

from . import context, paths


def next_version(ctx=None, ext=None):
    """One past the highest version on disk, or 1 when nothing is saved yet."""
    existing = paths.existing_versions(ctx, ext)
    return (existing[-1] + 1) if existing else 1


def latest_version(ctx=None, ext=None):
    """Highest version on disk, or None when the task has no scenes yet."""
    existing = paths.existing_versions(ctx, ext)
    return existing[-1] if existing else None


def version_in(path):
    """The version number written in a file name, or None.

    Publishing reads the version back out of the file the DCC actually saved
    rather than trusting the number it asked for, so a save that landed
    somewhere unexpected is caught instead of silently republished.
    """
    match = paths.VERSION_RE.search(os.path.basename(path or ""))
    return int(match.group(1)) if match else None


def next_scene_path(ctx=None, ext=None, create_dir=False):
    """Absolute path the next save should use.

    Raises ValueError when the launch carried no entity, because every caller
    has to tell the artist that rather than silently writing somewhere else.
    """
    ctx = ctx or context.get()
    folder = paths.work_dir(ctx)
    if not folder:
        raise ValueError(
            "This session was launched without a task, so ShotDeck does not "
            "know where to save. Pick a task in ShotDeck and relaunch.")

    if create_dir and not os.path.isdir(folder):
        os.makedirs(folder)

    path = paths.scene_path(next_version(ctx, ext), ctx, ext)
    if os.path.exists(path):
        # next_version() is one past the highest on disk, so this only fires
        # when the scan missed a file -- a different extension, or someone
        # saving into the folder at the same moment. Never overwrite.
        raise ValueError(
            "The next version already exists on disk:\n{0}\n\nSomeone may be "
            "working in the same folder. Check before saving.".format(path))
    return path
