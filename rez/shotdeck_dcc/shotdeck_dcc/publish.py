"""Saving a versioned work file from inside the DCC.

Scope note: this saves scenes, it does not create ShotGrid Versions. Publishing
media to ShotGrid stays in ShotDeck's own publish dialog, which already handles
preflight, media inspection, upload retries and note creation -- none of which
belongs in a package that has to load inside five different interpreters.

What the DCC side owes the artist is the boring half: work out the next version
number, make the folder, save there, and say where it went.
"""

from . import context, versioning


def save_next_version(adapter, ctx=None):
    """Save the open scene as the next version. Returns the path written.

    The adapter does the host-specific save; everything above it is shared.
    """
    ctx = ctx or context.get()
    path = versioning.next_scene_path(ctx, create_dir=True)
    adapter.save_scene(path)
    return path


def describe_target(ctx=None):
    """Where the next save would go, for a menu label or a confirmation.

    Returns a string either way -- callers put this in front of an artist, so
    "no task" has to read as an explanation, not as an error.
    """
    ctx = ctx or context.get()
    try:
        return versioning.next_scene_path(ctx)
    except ValueError as e:
        return str(e)
