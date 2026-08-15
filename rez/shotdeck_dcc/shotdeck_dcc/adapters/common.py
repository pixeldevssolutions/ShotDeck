"""What the menu actions actually do, written once for every host.

Each function takes the adapter module so it can call back into the two things
that are genuinely host-specific: save_scene() and message().
"""

import os
import subprocess
import sys

from .. import context, publish, versioning


def save_next_version(adapter):
    """Save the open scene as the next version and report where it went."""
    try:
        path = publish.save_next_version(adapter)
    except ValueError as e:                  # launched without a task
        adapter.message(str(e))
        return None
    except Exception as e:
        adapter.message("Save failed: {0}".format(e))
        return None

    adapter.message("Saved {0}".format(path))
    return path


def open_work_folder(adapter):
    """Open this task's scene folder in the desktop file manager."""
    from .. import paths

    folder = paths.work_dir()
    if not folder:
        adapter.message(
            "This session was launched without a task, so there is no work "
            "folder. Pick a task in ShotDeck and relaunch.")
        return None

    if not os.path.isdir(folder):
        adapter.message("Work folder does not exist yet:\n{0}".format(folder))
        return None

    opener = os.environ.get("SHOTDECK_FILE_MANAGER", "xdg-open")
    try:
        subprocess.Popen([opener, folder], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, ValueError) as e:
        # start_new_session is POSIX-only; the farm is Linux, but a developer
        # box should get the path rather than a traceback.
        adapter.message("Could not open {0}: {1}".format(folder, e))
        return None
    return folder


def show_context(adapter):
    """Print and show what ShotDeck launched this session with."""
    ctx = context.get()
    text = ctx.summary()
    try:
        text += "\nNext save    " + versioning.next_scene_path(ctx)
    except ValueError:
        text += "\nNext save    (no task selected)"

    sys.stdout.write(text + "\n")
    adapter.message(text)
    return text
