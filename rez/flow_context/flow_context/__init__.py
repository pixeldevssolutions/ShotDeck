"""Read the ShotGrid context that Flow handed to this DCC.

Publish tools inside Maya, Nuke, Blender and so on should import this rather
than reading FLOW_* environment variables directly, so the context file
format can change in one place.

    import flow_context

    ctx = flow_context.get()
    if ctx.task_id:
        publish_to_task(ctx.task_id, ctx.entity_type, ctx.entity_id)
    else:
        warn("Launched without a task — pick one in Flow first.")
"""

import json
import os

__version__ = "1.0.0"

CONTEXT_ENV_VAR = "FLOW_CONTEXT_FILE"

_cache = None


class Context(object):
    """A launch context. Every attribute is present even when empty."""

    def __init__(self, data=None):
        data = data or {}
        self._data = data
        task = data.get("task") or {}
        project = data.get("project") or {}
        user = data.get("user") or {}
        software = data.get("software") or {}

        self.site = data.get("site", "")
        self.project_id = project.get("id")
        self.project_name = project.get("name", "")
        self.project_code = project.get("code", "")
        self.user_login = user.get("login", "")
        self.user_email = user.get("email", "")
        self.software = software.get("code", "")
        self.software_version = software.get("version", "")

        self.task_id = task.get("id")
        self.task_name = task.get("name", "")
        self.step = task.get("step", "")
        self.entity_type = task.get("entity_type", "")
        self.entity_id = task.get("entity_id")
        self.entity_name = task.get("entity_name", "")

    def __bool__(self):
        """True when a project context was loaded at all."""
        return self.project_id is not None

    __nonzero__ = __bool__      # DCCs still on Python 2

    @property
    def has_task(self):
        """False when the app was launched without selecting a task."""
        return self.task_id is not None

    def as_dict(self):
        return dict(self._data)

    def __repr__(self):
        if not self:
            return "<Context empty>"
        return "<Context {0} / {1} / {2}>".format(
            self.project_name, self.entity_name or "-", self.task_name or "-")


def get(refresh=False):
    """The context for this session. Never raises — returns an empty Context
    when the app was not launched from Flow, so tools can degrade rather
    than traceback in front of an artist."""
    global _cache
    if _cache is not None and not refresh:
        return _cache
    _cache = Context(_load())
    return _cache


def _load():
    path = os.environ.get(CONTEXT_ENV_VAR)
    if not path or not os.path.isfile(path):
        return _from_env()
    try:
        with open(path) as f:
            return json.load(f)
    except (ValueError, OSError):
        # Truncated or unreadable file: the individual variables are still set.
        return _from_env()


def _from_env():
    """Fallback built from the flat FLOW_* variables."""
    def num(name):
        raw = os.environ.get(name, "")
        return int(raw) if raw.isdigit() else None

    if not os.environ.get("FLOW_PROJECT_ID"):
        return {}
    return {
        "schema": 1,
        "site": os.environ.get("FLOW_SITE", ""),
        "user": {
            "login": os.environ.get("FLOW_USER", ""),
            "email": os.environ.get("FLOW_USER_EMAIL", ""),
        },
        "project": {
            "id": num("FLOW_PROJECT_ID"),
            "name": os.environ.get("FLOW_PROJECT_NAME", ""),
            "code": os.environ.get("FLOW_PROJECT_CODE", ""),
        },
        "software": {
            "code": os.environ.get("FLOW_SOFTWARE", ""),
            "version": os.environ.get("FLOW_SOFTWARE_VERSION", ""),
        },
        "task": {
            "id": num("FLOW_TASK_ID"),
            "name": os.environ.get("FLOW_TASK_NAME", ""),
            "step": os.environ.get("FLOW_STEP", ""),
            "entity_type": os.environ.get("FLOW_ENTITY_TYPE", ""),
            "entity_id": num("FLOW_ENTITY_ID"),
            "entity_name": os.environ.get("FLOW_ENTITY_NAME", ""),
        } if num("FLOW_TASK_ID") else None,
    }
