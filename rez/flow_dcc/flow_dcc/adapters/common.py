"""What the menu actions actually do, written once for every host.

Each function takes the adapter module and calls back into the handful of
things that are genuinely host-specific: save_scene(), current_scene(),
message(), confirm(), and ask_path().
"""

import functools
import os
import subprocess
import sys

from .. import context, deadline, paths, publish, versioning


def save(adapter):
    """Save over the open scene, or fall through to Version Up if unsaved.

    Saving an untitled scene has no obvious destination, and silently picking
    one is how work ends up outside the pipeline -- so route it to the action
    that does know where scenes go.
    """
    current = adapter.current_scene()
    if not current:
        adapter.message(
            "This scene has never been saved, so Flow does not know which "
            "file to save over. Using Version Up instead.")
        return version_up(adapter)

    try:
        adapter.save_scene(current)
    except Exception as e:
        adapter.message("Save failed: {0}".format(e))
        return None

    adapter.message("Saved {0}".format(current))
    return current


def save_as(adapter):
    """Save to a path the artist picks, pre-filled with the correct name.

    The dialog opens on the task's work folder with the next pipeline name
    already in it, so the convention is what an artist gets by pressing
    Enter -- Save As is for the exception, not for naming.
    """
    start = paths.work_dir() or os.path.expanduser("~")
    try:
        suggested = os.path.basename(versioning.next_scene_path())
    except ValueError:
        suggested = ""                  # no task: let the host decide

    path = adapter.ask_path(start, paths.extension(), suggested)
    if not path:
        return None                     # cancelled

    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    try:
        adapter.save_scene(path)
    except Exception as e:
        adapter.message("Save As failed: {0}".format(e))
        return None

    if not _under(path, paths.work_dir()):
        adapter.message(
            "Saved {0}\n\nNote: this is outside the task's work folder, so "
            "Flow will not count it when working out the next version."
            .format(path))
    else:
        adapter.message("Saved {0}".format(path))
    return path


def version_up(adapter):
    """Save the open scene as the next version in the task's work folder."""
    try:
        path = publish.save_next_version(adapter)
    except ValueError as e:                  # launched without a task
        adapter.message(str(e))
        return None
    except Exception as e:
        adapter.message("Version Up failed: {0}".format(e))
        return None

    adapter.message("Saved {0}".format(path))
    return path


def publish_scene(adapter):
    """Confirm the destination, then run the publish pipeline."""
    try:
        work_path, publish_path, version = publish.prepare()
    except publish.PublishError as e:
        adapter.message(str(e))
        return None

    ctx = context.get()
    if not adapter.confirm(
            "Publish v{0:03d} of {1} / {2}?\n\n"
            "Work file   {3}\nPublish     {4}\n\n"
            "The scene will be saved first."
            .format(version, ctx.entity_name, ctx.task_name,
                    work_path, publish_path)):
        return None

    try:
        result = publish.publish(adapter)
    except publish.PublishError as e:
        adapter.message(str(e))
        return None
    except Exception as e:
        adapter.message("Publish failed: {0}".format(e))
        return None

    adapter.message(result.summary())
    return result


def submit_to_deadline(adapter):
    """Save the scene, confirm the job, hand it to the farm.

    The save is not optional and not a version up: the farm renders the file
    that is on disk, so submitting without saving queues yesterday's scene --
    the one bug in a submitter that costs a whole farm night. An unsaved scene
    has no file to save over, so that case routes to Version Up as Save does.
    """
    current = adapter.current_scene()
    if not current:
        if not version_up(adapter):
            return None
    else:
        try:
            adapter.save_scene(current)
        except Exception as e:
            adapter.message("Could not save before submitting: {0}".format(e))
            return None

    try:
        plugin_name, scene = deadline.validate(adapter)
        frames = deadline.frames(adapter)
    except deadline.DeadlineError as e:
        adapter.message(str(e))
        return None

    ctx = context.get()
    if not adapter.confirm(
            "Submit {0} to Deadline?\n\n"
            "Plugin      {1}\nFrames      {2}\nPool        {3}\n"
            "Scene       {4}"
            .format(ctx.task_name or "this scene", plugin_name, frames,
                    deadline.POOL, scene)):
        return None

    try:
        job = deadline.submit(adapter)
    except deadline.DeadlineError as e:
        adapter.message(str(e))
        return None
    except Exception as e:
        adapter.message("Submit to Deadline failed: {0}".format(e))
        return None

    adapter.message(job.summary())
    return job


def open_work_folder(adapter):
    return _open(adapter, paths.work_dir(), "work")


def open_publish_folder(adapter):
    return _open(adapter, paths.publish_dir(), "publish")


def show_context(adapter):
    """The Context panel: coordinates, then where the next save would land."""
    ctx = context.get()
    text = ctx.summary()
    try:
        text += "\n\nNext save   " + versioning.next_scene_path(ctx)
        text += "\nNext publish " + paths.publish_path(
            versioning.next_version(ctx), ctx)
    except ValueError:
        text += "\n\nNo task selected, so there is nowhere to save or publish."

    sys.stdout.write(text + "\n")
    adapter.message(text)
    return text


# -- helpers --------------------------------------------------------------

def _open(adapter, folder, label):
    if not folder:
        adapter.message(
            "This session was launched without a task, so there is no {0} "
            "folder. Pick a task in Flow and relaunch.".format(label))
        return None
    if not os.path.isdir(folder):
        adapter.message("The {0} folder does not exist yet:\n{1}".format(
            label, folder))
        return None

    opener = os.environ.get("FLOW_FILE_MANAGER", "xdg-open")
    try:
        subprocess.Popen([opener, folder], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, ValueError) as e:
        # start_new_session is POSIX-only; the farm is Linux, but a developer
        # box should get the path rather than a traceback.
        adapter.message("Could not open {0}: {1}".format(folder, e))
        return None
    return folder


def _under(path, folder):
    if not folder:
        return False
    return os.path.normpath(path).startswith(os.path.normpath(folder) + os.sep)


# -- wiring ---------------------------------------------------------------

# Menu attribute -> the function above it. ACTIONS names these; adapters get
# them from bind() rather than writing seven one-line wrappers each.
ACTION_FUNCS = {
    "action_save": save,
    "action_save_as": save_as,
    "action_version_up": version_up,
    "action_publish": publish_scene,
    "action_submit": submit_to_deadline,
    "action_open_work_folder": open_work_folder,
    "action_open_publish_folder": open_publish_folder,
    "action_context": show_context,
}


def bind(module):
    """Give an adapter module its action_* entry points.

    An action the adapter already defines is left alone: a host whose file
    dialog cannot answer synchronously (Blender) has to own its own Save As,
    and overwriting it here would silently undo that.
    """
    for name, func in ACTION_FUNCS.items():
        if not hasattr(module, name):
            setattr(module, name, functools.partial(func, module))
    return module
