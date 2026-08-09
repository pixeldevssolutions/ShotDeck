"""Everything that must be true before ShotGrid is touched.

One place, run twice: once when the artist picks a file, so the dialog can say
what is wrong while it is still cheap to fix, and again inside the publish
service immediately before the Version is created. The second run is the one
that counts -- a dialog can sit open for an hour while a file is moved,
overwritten or unmounted, and the client's opinion of a path is not a
guarantee.

No Qt. The dialog renders a report; it does not decide what is in one.
"""

import os

import applog
import config
import media_inspector
import path_validator
from path_validator import Finding, ERROR, WARNING, INFO

log = applog.get()


class Report:
    """The findings, grouped the way the dialog shows them."""

    # Path before Media on purpose: if the file belongs to another show, that
    # is the finding worth reporting, not that this machine cannot see it.
    SECTIONS = ("Context", "Path", "Media", "Version", "Authentication")

    def __init__(self):
        self.sections = {name: [] for name in self.SECTIONS}
        self.media_info = None

    def add(self, section, level, code, message, detail=""):
        self.sections[section].append(Finding(level, code, message, detail))

    def ok(self, section, message):
        self.add(section, INFO, "ok", message)

    # -- reading it --------------------------------------------------------

    @property
    def findings(self):
        out = []
        for name in self.SECTIONS:
            out.extend(self.sections[name])
        return out

    @property
    def errors(self):
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == WARNING]

    @property
    def passed(self):
        """No errors. Warnings are the artist's call, errors are not."""
        return not self.errors

    def summary(self):
        if self.errors:
            return self.errors[0].message
        if self.warnings:
            return self.warnings[0].message
        return "Ready to publish."

    def __repr__(self):
        return (f"<Report {len(self.errors)} errors "
                f"{len(self.warnings)} warnings>")


def run(sg, project, task, name, media_path, policy=None,
        check_name=True):
    """Build a Report for this publish. Never raises."""
    report = Report()
    _context(report, project, task)
    info = _media(report, media_path)
    report.media_info = info
    _path(report, media_path, project, policy)
    if check_name:
        _version_name(report, sg, project, task, name)
    _auth(report, sg)
    return report


# -- the checks -------------------------------------------------------------

def _context(report, project, task):
    if not project or not project.get("id"):
        report.add("Context", ERROR, "no_project", "No project is open.")
        return
    report.ok("Context", f"Project: {project.get('name')}")

    if not task or not task.get("id"):
        report.add("Context", ERROR, "no_task",
                   "No task selected. Publish from a task in My Tasks so the "
                   "Version lands on the right shot.")
        return

    entity = task.get("entity")
    if not entity:
        report.add("Context", ERROR, "no_entity",
                   f"Task '{task.get('content', '')}' is not linked to a shot "
                   f"or asset, so a Version has nothing to attach to.")
    else:
        report.ok("Context", f"{entity.get('type')}: {entity.get('name')}")
    report.ok("Context", f"Task: {task.get('content', '')}")
    step = (task.get("step") or {}).get("name")
    if step:
        report.ok("Context", f"Department: {step}")


def _media(report, path):
    """Existence, readability, size, format -- then what it actually is."""
    if not path:
        report.add("Media", ERROR, "no_media",
                   "Choose a movie or an image to publish.")
        return None
    if not os.path.isfile(path):
        report.add("Media", ERROR, "missing",
                   f"The media file does not exist:\n{path}")
        return None
    if not os.access(path, os.R_OK):
        report.add("Media", ERROR, "unreadable",
                   f"The media file cannot be read. Check its permissions:\n"
                   f"{path}")
        return None

    size = os.path.getsize(path)
    if size == 0:
        report.add("Media", ERROR, "empty",
                   "The media file is zero bytes — an interrupted render or "
                   "a copy that never finished.")
        return None

    kind = config.media_kind(path)
    if not kind:
        ext = os.path.splitext(path)[1] or "(no extension)"
        report.add("Media", ERROR, "unsupported",
                   f"{ext} is not a media format ShotDeck publishes.\n\n"
                   f"Movies: {', '.join(sorted(config.MOVIE_EXTENSIONS))}\n"
                   f"Images: {', '.join(sorted(config.IMAGE_EXTENSIONS))}")
        return None

    report.ok("Media", "File exists and is readable")
    info = media_inspector.inspect(path)
    _media_contents(report, info)
    return info


def _media_contents(report, info):
    """What the file turns out to contain, which the extension only claims.

    A .mov that ffprobe cannot decode is a corrupt or misnamed file, and
    publishing it means a review session that fails at the worst moment. Only
    an inspector that actually ran can say so -- without ffprobe this stays
    quiet rather than guessing.
    """
    report.ok("Media", f"{info.container.upper()} container, "
                       f"{media_inspector.human_size(info.size)}")

    if not info.source:
        if info.error:
            report.add("Media", WARNING, "uninspectable",
                       f"The media could not be inspected "
                       f"({info.error}). ShotDeck cannot confirm it is "
                       f"playable before uploading it.")
        else:
            report.add("Media", INFO, "no_inspector",
                       "ffprobe is not installed here, so the media was not "
                       "inspected.")
        return

    if info.kind == "movie" and not (info.width and info.height):
        report.add("Media", ERROR, "mismatch",
                   f"The extension says {info.container.upper()}, but no "
                   f"video track was found in the file. It is corrupt, "
                   f"truncated, or not the format its name claims.")
        return

    if info.resolution:
        report.ok("Media", info.resolution)
    if info.fps:
        report.ok("Media", f"{info.fps:g} fps")
    if info.frames:
        report.ok("Media", f"{info.frames} frames")
    if info.codec:
        report.ok("Media", f"Codec: {info.codec}")
    report.ok("Media", "Media inspection successful")


def _path(report, media_path, project, policy):
    """Where the file claims to be, checked whether or not it is there.

    Run for a missing file too: a path under another show is wrong for a
    reason that has nothing to do with whether this workstation can see it,
    and "belongs to SHOW002" is a more useful thing to be told than "not
    found".
    """
    if not media_path:
        return          # already reported by _media
    findings = path_validator.validate(media_path, project, policy)
    for finding in findings:
        report.sections["Path"].append(finding)
    if not any(f.level in (ERROR, WARNING) for f in findings):
        report.ok("Path", "Approved project path")


def _version_name(report, sg, project, task, name):
    name = (name or "").strip()
    if not name:
        report.add("Version", ERROR, "no_name",
                   "Give the version a name.")
        return
    if not task or not task.get("id") or not project:
        return
    try:
        clash = sg.version_exists(project, name, task["id"])
    except Exception as e:
        # Not being allowed to look is not the same as the name being free;
        # say so, and let the create be the gate.
        log.warning("could not check for an existing Version: %s", e)
        report.add("Version", WARNING, "name_uncheckable",
                   f"ShotGrid would not confirm whether {name} already "
                   f"exists ({e}).")
        return
    if clash:
        report.add("Version", ERROR, "duplicate",
                   f"A Version named {name} already exists on this task.\n\n"
                   f"Choose another name — nothing is ever overwritten.",
                   f"Version {clash['id']}")
        return
    report.ok("Version", f"Version name available: {name}")


def _auth(report, sg):
    """Which identity is about to write, and whether the artist is known."""
    if sg is None:
        return
    report.ok("Authentication",
              f"ShotGrid API identity: {getattr(sg, 'api_identity', '?')}")
    owner = getattr(sg, "owner", None)
    if owner:
        report.ok("Authentication",
                  f"Version credited to: {owner.get('name') or owner.get('id')}")
    else:
        report.add("Authentication", WARNING, "no_owner",
                   "No ShotGrid user matched your email address, so the "
                   "Version will be created without an artist credit.")
