"""Work out where a task lives on disk, and open it."""

import os
import shutil
import subprocess

import applog
import config

log = applog.get()


def entity_root(project, task):
    """Top folder for the task's shot or asset, e.g.
    /jobs/UAT6/sequences/SEQ001/shots/AD1030. None if we can't fill the
    template -- usually a shot with no sequence linked."""
    entity = (task or {}).get("entity") or {}
    kind = entity.get("type")
    template = config.ENTITY_PATH_TEMPLATES.get(kind)
    if not template:
        return None

    tokens = {
        "project": project.get("tank_name") or project["name"],
        "project_name": project["name"],
        "entity": entity.get("name", ""),
        "shot": entity.get("name", ""),
        "asset": entity.get("name", ""),
        "sequence": _sequence(task),
        "asset_type": task.get("entity.Asset.sg_asset_type") or "",
        "step": (task.get("step") or {}).get("name", ""),
    }
    try:
        path = template.format(**tokens)
    except KeyError as e:
        log.warning("path template for %s wants unknown token %s", kind, e)
        return None
    if "//" in path.replace("://", ""):     # a token came back empty
        log.warning("incomplete path for %s: %s", entity.get("name"), path)
        return None
    return path


def _sequence(task):
    seq = task.get("entity.Shot.sg_sequence")
    if isinstance(seq, dict):
        return seq.get("name", "")
    return seq or ""


def folders(project, task):
    """[(label, path, exists), ...] for the right-click menu. Everything in
    config.ENTITY_SUBFOLDERS, plus the root itself."""
    root = entity_root(project, task)
    if not root:
        return []

    out = [("Shot folder" if (task.get("entity") or {}).get("type") == "Shot"
            else "Asset folder", root, os.path.isdir(root))]

    step = ((task.get("step") or {}).get("name") or "").lower()
    for label, rel in config.ENTITY_SUBFOLDERS:
        if "{step}" in rel and not step:
            continue
        # Always POSIX separators -- these live on the Linux farm even when
        # Flow is being developed on Windows.
        path = root.rstrip("/") + "/" + rel.format(step=step)
        out.append((label.format(step=step or "step"), path, os.path.isdir(path)))
    return out


def open_url(url):
    """Open a ShotGrid page in the desktop browser.

    Same opener as the folders, because xdg-open is the desktop's own idea of
    what a URL should do -- Flow does not need its own browser handling.
    """
    opener = config.FILE_MANAGER
    if opener and shutil.which(opener.split()[0]) is None:
        raise RuntimeError(
            f"{opener.split()[0]} is not installed, so the page can't be "
            f"opened.\n\nURL:\n{url}")
    log.info("opening %s", url)
    subprocess.Popen(opener.split() + [url], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_folder(path):
    """Hand the folder to whatever file manager the desktop uses."""
    if not os.path.isdir(path):
        raise RuntimeError(f"Folder does not exist:\n{path}")

    opener = config.FILE_MANAGER
    if opener and shutil.which(opener.split()[0]) is None:
        raise RuntimeError(
            f"{opener.split()[0]} is not installed, so the folder can't be "
            f"opened.\n\nPath:\n{path}")

    cmd = opener.split() + [path]
    log.info("opening folder: %s", path)
    subprocess.Popen(cmd, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
