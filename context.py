"""ShotGrid context handed to a launched DCC.

A launch writes a small JSON file and points SHOTDECK_CONTEXT_FILE at it. The
individual SHOTDECK_* variables carry the same information for shell scripts and
for rez package commands() blocks that cannot parse JSON.

DCC-side code should not read these variables directly -- import the
`shotdeck_context` rez package instead (see rez/shotdeck_context/), so the
shape of the file can change without breaking every publish tool.
"""

import getpass
import json
import os
import socket
import time
import uuid

import config
import paths

CONTEXT_DIR = os.environ.get(
    "SHOTDECK_CONTEXT_DIR", os.path.expanduser("~/.shotdeck/context"))

# Contexts older than this are removed on the next launch.
CONTEXT_MAX_AGE_SECONDS = 7 * 24 * 3600


def build(project, software, task=None, login=None, email=None):
    """Assemble the context dictionary for one launch."""
    entity = (task or {}).get("entity") or {}
    step = (task or {}).get("step") or {}
    return {
        "schema": 1,
        "created": time.time(),
        "site": config.SG_SITE,
        "host": socket.gethostname(),
        # Resolved here, where the templates live, so in-DCC tools never have
        # to carry a second copy of ENTITY_PATH_TEMPLATES.
        "entity_root": paths.entity_root(project, task) if task else "",
        "user": {
            "login": login or getpass.getuser(),
            "email": email or "",
        },
        "project": {
            "id": project["id"],
            "name": project["name"],
            # Same fallback env_resolver uses, so the code matches the folder
            # name when a project has no tank_name set.
            "code": (project.get("tank_name")
                     or project["name"].replace(" ", "_").lower()),
        },
        "software": {
            "code": software.get("code") if software else "",
            "version": software.get("version") if software else "",
            "rez_packages": (software.get("sg_rez_packages") or "").split()
            if software else [],
        },
        "task": {
            "id": task["id"],
            "name": task.get("content") or "",
            "status": task.get("sg_status_list") or "",
            "step": step.get("name") or "",
            "entity_type": entity.get("type") or "",
            "entity_id": entity.get("id"),
            "entity_name": entity.get("name") or "",
        } if task else None,
    }


def write(ctx):
    """Write the context to disk and return its path."""
    os.makedirs(CONTEXT_DIR, exist_ok=True)
    _prune()
    path = os.path.join(CONTEXT_DIR, f"{uuid.uuid4().hex}.json")
    with open(path, "w") as f:
        json.dump(ctx, f, indent=2)
    return path


def env(ctx, path):
    """Flatten the context into environment variables for the launched process."""
    task = ctx.get("task") or {}
    out = {
        "SHOTDECK_CONTEXT_FILE": path,
        "SHOTDECK_SITE": ctx["site"],
        "SHOTDECK_USER": ctx["user"]["login"],
        "SHOTDECK_USER_EMAIL": ctx["user"]["email"],
        "SHOTDECK_PROJECT_ID": str(ctx["project"]["id"]),
        "SHOTDECK_PROJECT_NAME": ctx["project"]["name"],
        "SHOTDECK_PROJECT_CODE": ctx["project"]["code"],
        "SHOTDECK_SOFTWARE": ctx["software"]["code"],
        "SHOTDECK_SOFTWARE_VERSION": ctx["software"]["version"] or "",
        # Present but empty when the app was launched with no task selected,
        # so publish tools can tell "no context" from "variable missing".
        "SHOTDECK_TASK_ID": str(task.get("id") or ""),
        "SHOTDECK_TASK_NAME": task.get("name") or "",
        "SHOTDECK_STEP": task.get("step") or "",
        "SHOTDECK_ENTITY_TYPE": task.get("entity_type") or "",
        "SHOTDECK_ENTITY_ID": str(task.get("entity_id") or ""),
        "SHOTDECK_ENTITY_NAME": task.get("entity_name") or "",
        # Where this task's scenes live. shotdeck_dcc builds work paths from
        # this rather than re-deriving the templates on the DCC side.
        "SHOTDECK_ENTITY_ROOT": ctx.get("entity_root") or "",
    }
    return out


def _prune():
    """Delete stale context files so ~/.shotdeck does not grow without bound."""
    cutoff = time.time() - CONTEXT_MAX_AGE_SECONDS
    try:
        names = os.listdir(CONTEXT_DIR)
    except OSError:
        return
    for name in names:
        if not name.endswith(".json"):
            continue
        p = os.path.join(CONTEXT_DIR, name)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass   # another session may have removed it already
