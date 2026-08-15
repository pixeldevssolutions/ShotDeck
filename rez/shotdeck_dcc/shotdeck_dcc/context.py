"""The launch context, as the DCC sees it.

shotdeck_context already parses the context file ShotDeck writes; this is a
thin, DCC-facing view over it that never raises and never needs the file to
exist. Outside a ShotDeck launch every field is empty and `has_task` is False,
so a menu action can say "relaunch from ShotDeck" instead of tracebacking at an
artist mid-shot.
"""

import os

# Variables the adapters and the verification steps depend on.
REQUIRED = [
    "SHOTDECK_PROJECT_NAME",
    "SHOTDECK_ENTITY_NAME",
    "SHOTDECK_TASK_NAME",
    "SHOTDECK_STEP",
    "SHOTDECK_SOFTWARE",
]


class Context(object):
    """Flat, read-only view of one ShotDeck launch."""

    def __init__(self, data=None):
        data = data or {}
        project = data.get("project") or {}
        software = data.get("software") or {}
        task = data.get("task") or {}

        self.project_name = project.get("name") or _env("SHOTDECK_PROJECT_NAME")
        self.project_code = project.get("code") or _env("SHOTDECK_PROJECT_CODE")
        self.project_id = project.get("id") or _int("SHOTDECK_PROJECT_ID")
        self.software = (software.get("code")
                         or _env("SHOTDECK_SOFTWARE")).lower()
        self.software_version = (software.get("version")
                                 or _env("SHOTDECK_SOFTWARE_VERSION"))
        self.task_id = task.get("id") or _int("SHOTDECK_TASK_ID")
        self.task_name = task.get("name") or _env("SHOTDECK_TASK_NAME")
        self.step = task.get("step") or _env("SHOTDECK_STEP")
        self.entity_type = task.get("entity_type") or _env("SHOTDECK_ENTITY_TYPE")
        self.entity_id = task.get("entity_id") or _int("SHOTDECK_ENTITY_ID")
        self.entity_name = task.get("entity_name") or _env("SHOTDECK_ENTITY_NAME")
        self.user = _env("SHOTDECK_USER")
        # Written by ShotDeck, which already knows the templates. The DCC side
        # deliberately does not re-derive it -- one convention, one place.
        self.entity_root = _env("SHOTDECK_ENTITY_ROOT")

    @property
    def has_task(self):
        return bool(self.task_id)

    def missing(self):
        """Which REQUIRED variables are not set. Empty list means a good launch."""
        return [name for name in REQUIRED if not os.environ.get(name)]

    def __bool__(self):
        return bool(self.project_name or self.task_id)

    __nonzero__ = __bool__          # DCCs still shipping Python 2 interpreters

    def __repr__(self):
        return ("<ShotDeck context project={0!r} entity={1!r} task={2!r} "
                "step={3!r} software={4!r}>".format(
                    self.project_name, self.entity_name, self.task_name,
                    self.step, self.software))

    def summary(self):
        """Multi-line text for the "Show context" menu action."""
        rows = [
            ("Project", self.project_name),
            ("Entity", "{0} ({1})".format(self.entity_name, self.entity_type)
             if self.entity_type else self.entity_name),
            ("Task", self.task_name),
            ("Step", self.step),
            ("Software", "{0} {1}".format(self.software, self.software_version)
             .strip()),
            ("Work folder", self.entity_root or "(not set)"),
            ("User", self.user),
        ]
        return "\n".join("{0:<12}{1}".format(k, v or "-") for k, v in rows)


def _env(name):
    return os.environ.get(name, "")


def _int(name):
    raw = os.environ.get(name, "")
    return int(raw) if raw.isdigit() else None


def get():
    """The current context. Prefers shotdeck_context, falls back to the env.

    shotdeck_context may legitimately be missing: launcher.py skips injecting
    it when it has not been released yet, and the flat SHOTDECK_* variables are
    exported either way.
    """
    try:
        import shotdeck_context
    except ImportError:
        return Context()

    try:
        return Context(shotdeck_context.get().as_dict())
    except Exception:               # a broken context file must not stop a DCC
        return Context()
