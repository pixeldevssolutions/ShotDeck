"""Is this file somewhere a publish is allowed to point at?

The failure this exists to prevent is quiet and expensive: a Version whose media
lives on the artist's desktop looks fine in the dialog, uploads happily, and
then cannot be found by the farm, by review, or by whoever picks the shot up
next. Catching it costs one `os.path.realpath` call; not catching it costs a
day.

Containment is done with `os.path.commonpath` on normalised, symlink-resolved
paths, never with `startswith` -- `/jobs/SHOW001_backup` starts with
`/jobs/SHOW001` and is a different show.

No Qt, no ShotGrid: this is pure path arithmetic and is tested as such.
"""

import os

import applog
import config

log = applog.get()

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"


class Finding:
    """One thing worth saying about the path, at one severity."""

    def __init__(self, level, code, message, detail=""):
        self.level = level
        self.code = code
        self.message = message
        self.detail = detail

    @property
    def blocking(self):
        return self.level == ERROR

    def __repr__(self):
        return f"<{self.level} {self.code}: {self.message}>"


# -- normalising ------------------------------------------------------------

def normalise(path):
    """Absolute, expanded, symlink-resolved, separator-normalised.

    `realpath` matters more than it looks: an artist's `~/renders` is often a
    symlink into the project, and a project path is sometimes reached through a
    different mount point than the one the templates name.
    """
    if not path:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(str(path)))
    try:
        resolved = os.path.realpath(os.path.abspath(expanded))
    except OSError:                                  # pragma: no cover
        resolved = os.path.abspath(expanded)
    return resolved.replace("\\", "/").rstrip("/") or resolved


def _key(path):
    """Comparison form: case-folded where the filesystem is."""
    return path.lower() if os.name == "nt" else path


def contains(root, path):
    """True when `path` is `root` or sits inside it.

    Not `startswith`: that matches SHOW001_backup against SHOW001. Not
    `relpath` alone either, which happily walks up with `..`.
    """
    root, path = normalise(root), normalise(path)
    if not root or not path:
        return False
    root_key, path_key = _key(root), _key(path)
    if root_key == path_key:
        return True
    try:
        common = os.path.commonpath([root_key, path_key])
    except ValueError:
        # Different drives on Windows, or one relative and one absolute.
        return False
    # commonpath hands back the platform separator, so it has to be brought
    # back to the one form everything here compares in.
    return common.replace("\\", "/").rstrip("/") == root_key


# -- where the project lives ------------------------------------------------

def project_root(project):
    """The project's folder on disk, from the templates the launcher uses.

    `ENTITY_PATH_TEMPLATES` already encodes the studio's convention
    (`/jobs/{project}/sequences/...`); the root is the part of it that is fixed
    once the project is known. Nothing new is invented here, so a studio that
    changes the template changes this too.
    """
    if not project:
        return ""
    tokens = {
        "project": project.get("tank_name") or project.get("name") or "",
        "project_name": project.get("name") or "",
    }
    roots = []
    for template in config.ENTITY_PATH_TEMPLATES.values():
        head = []
        for part in template.split("/"):
            if "{" in part and not _fills(part, tokens):
                break
            head.append(part.format(**tokens) if "{" in part else part)
        if len(head) > 1:
            roots.append("/".join(head))
    if not roots:
        return ""
    # Several templates, one project: their common head is the project root.
    # Compared as written, not case-folded -- the answer is a path that gets
    # shown to people.
    try:
        return normalise(os.path.commonpath(roots))
    except ValueError:                               # pragma: no cover
        return normalise(roots[0])


def _fills(part, tokens):
    try:
        part.format(**tokens)
    except (KeyError, IndexError):
        return False
    return True


def approved_roots(project):
    """Everywhere this project may legitimately publish from."""
    tokens = {
        "project": project.get("tank_name") or project.get("name") or "",
        "project_name": project.get("name") or "",
    }
    roots = []
    root = project_root(project)
    if root:
        roots.append(root)
    for template in config.APPROVED_MEDIA_ROOTS:
        try:
            roots.append(normalise(template.format(**tokens)))
        except (KeyError, IndexError):
            log.warning("approved media root %r has an unknown token",
                        template)
    return roots


# -- the check itself -------------------------------------------------------

def validate(path, project, policy=None):
    """[Finding, ...] about where this file is. Empty means nothing to say.

    Severity depends on `config.PATH_POLICY`, except for a file that belongs to
    a different show -- that is wrong under every policy, because publishing
    SHOW002's render onto SHOW001 is not a preference.
    """
    policy = (policy or config.PATH_POLICY or "warn").lower()
    findings = []
    if not path:
        return [Finding(ERROR, "no_media", "Choose a file to publish.")]

    resolved = normalise(path)
    roots = approved_roots(project)
    root = project_root(project)

    literal = os.path.abspath(os.path.expandvars(os.path.expanduser(
        str(path)))).replace("\\", "/").rstrip("/")
    if _key(literal) != _key(resolved):
        # Worth saying out loud: the path being checked is not the path the
        # artist typed, and a symlink is exactly how media that looks local
        # turns out to be on the project, or the other way round.
        findings.append(Finding(
            INFO, "resolved",
            f"That path is a link. It resolves to:\n{resolved}"))

    # Inside the project: nothing more to say.
    if root and contains(root, resolved):
        findings.append(Finding(
            INFO, "in_project",
            f"Inside the project: {root}"))
        return findings

    other = _other_project(resolved, project)
    if other:
        findings.append(Finding(
            ERROR, "wrong_project",
            f"That file belongs to another project ({other}).\n\n"
            f"This publish is going to "
            f"{project.get('tank_name') or project.get('name')}. Publishing "
            f"one show's media onto another is never right.",
            resolved))
        return findings

    approved = next((r for r in roots if contains(r, resolved)), "")
    if approved:
        findings.append(Finding(
            INFO, "approved_external",
            f"In an approved location outside the project: {approved}"))
        return findings

    unsafe = _unsafe_part(resolved)
    if unsafe:
        findings.append(Finding(
            ERROR if policy in ("strict", "approved_only") else WARNING,
            "local_scratch",
            f"That file is in a local or temporary location "
            f"(“{unsafe}”).\n\nRender nodes and review systems cannot read "
            f"it, so the Version would point at media only this machine can "
            f"see.", resolved))
        return findings

    level = {"strict": ERROR, "approved_only": ERROR}.get(policy, WARNING)
    findings.append(Finding(
        level, "outside_project",
        f"That file is outside the approved project paths.\n\n"
        f"Selected:\n{resolved}\n\n"
        f"Project root:\n{root or 'not configured'}\n\n"
        f"Media published from here may not be reachable by other artists, "
        f"render machines or review.", resolved))
    return findings


def _other_project(resolved, project):
    """The name of the show this path belongs to, if it is a different one."""
    jobs = normalise(config.JOBS_ROOT)
    if not jobs or not contains(jobs, resolved):
        return ""
    relative = _key(resolved)[len(_key(jobs)):].strip("/")
    if not relative:
        return ""
    first = relative.split("/")[0]
    mine = (project.get("tank_name") or project.get("name") or "")
    return "" if _key(first) == _key(mine) else first


def _unsafe_part(resolved):
    parts = [p for p in _key(resolved).split("/") if p]
    for unsafe in config.UNSAFE_PATH_PARTS:
        unsafe = _key(unsafe)
        if "/" in unsafe:
            if f"/{unsafe}/" in f"/{'/'.join(parts)}/":
                return unsafe
        elif unsafe in parts[:-1]:      # the file's own name does not count
            return unsafe
    return ""


def describe_policy(policy=None):
    policy = (policy or config.PATH_POLICY or "warn").lower()
    return {
        "strict": "Media must be inside the project.",
        "approved_only": "Media must be inside the project or an approved "
                         "location.",
        "warn": "Media outside the project is allowed with a warning.",
    }.get(policy, f"Unknown path policy {policy!r}; treated as warn.")
