"""The standalone publish, as a service rather than as dialog code.

Nothing here imports Qt, so the whole publish can be exercised headlessly and
the dialog is left with nothing to do but collect input and show progress.

Two identities are involved and they are not the same thing:

  * the API request authenticates as the script user, `SG_SCRIPT_NAME`
    (`SG_daemon` here), which is what lets artists publish without a ShotGrid
    seat of their own;
  * the Version's `user` field credits the artist ShotDeck resolved at startup
    from their email address.

`SGClient.create_version` is where that is enforced. Nothing in this module
should ever set `user` to the script.
"""

import os
import time

import applog
import config
import media_inspector
import preflight

log = applog.get()


# -- errors -----------------------------------------------------------------

class PublishError(RuntimeError):
    """Something an artist can be shown as-is.

    `detail` carries the raw API text for the log; the message itself is
    written for someone who does not know what a ShotGrid filter is.
    """

    title = "Publish failed"

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.detail = detail or ""


class ContextError(PublishError):
    title = "Cannot publish to this task"


class MediaError(PublishError):
    title = "Media problem"


class DuplicateVersionError(PublishError):
    title = "Version already exists"


class PermissionDenied(PublishError):
    title = "Not permitted"


class AuthFailed(PublishError):
    title = "ShotGrid authentication failed"


class ConnectionFailed(PublishError):
    title = "ShotGrid unavailable"


class PathRejected(PublishError):
    title = "Media path rejected"


class WarningsNotAccepted(PublishError):
    title = "Publish needs confirming"


class PublishCancelled(PublishError):
    title = "Publish cancelled"


# Which finding maps to which error, so a preflight failure arrives at the
# dialog as the same kind of thing an API failure would.
_FINDING_ERRORS = {
    "no_project": ContextError, "no_task": ContextError,
    "no_entity": ContextError,
    "no_media": MediaError, "missing": MediaError, "unreadable": MediaError,
    "empty": MediaError, "unsupported": MediaError, "mismatch": MediaError,
    "wrong_project": PathRejected, "outside_project": PathRejected,
    "local_scratch": PathRejected,
    "duplicate": DuplicateVersionError, "no_name": PublishError,
}


def friendly(error, stage=""):
    """Turn whatever the API threw into something worth showing an artist."""
    text = str(error)
    low = text.lower()

    if any(w in low for w in ("permission", "not permitted", "denied",
                              "does not have access", "read-only",
                              "read only")):
        return PermissionDenied(
            "Your ShotGrid account does not have permission to create or "
            "upload Versions for this task.\n\n"
            "Contact Pipeline if this appears incorrect.", text)

    if any(w in low for w in ("authenticat", "invalid script", "api key",
                              "api_key", "script name")):
        return AuthFailed(
            "ShotGrid rejected ShotDeck's credentials. The service account "
            "may have been disabled or its key rotated.\n\n"
            "Contact Pipeline.", text)

    if any(w in low for w in ("timed out", "timeout", "connection",
                              "unreachable", "getaddrinfo", "max retries",
                              "ssl", "temporarily unavailable")):
        return ConnectionFailed(
            "ShotGrid could not be reached. Check the network and try "
            "again — nothing was published.", text)

    where = f" while {stage}" if stage else ""
    return PublishError(f"ShotGrid rejected the publish{where}.", text)


# -- models -----------------------------------------------------------------

class PublishRequest:
    """Everything the artist chose, in one object."""

    def __init__(self, project, task, name, media_path, description="",
                 work_file="", accepted_warnings=False, note=""):
        self.project = project
        self.task = task
        self.name = (name or "").strip()
        self.media_path = media_path or ""
        self.description = (description or "").strip()
        self.work_file = work_file or ""
        # The artist pressed "Continue anyway" on a warning. Carried into the
        # service rather than left in the dialog, so the decision is checked
        # where the publish actually happens.
        self.accepted_warnings = bool(accepted_warnings)
        self.note = (note or "").strip()


class PublishResult:
    def __init__(self, version, media_info=None, elapsed=0.0,
                 work_file_note="", work_file_error="", note_error=""):
        self.version = version
        self.media_info = media_info
        self.elapsed = elapsed
        self.work_file_note = work_file_note
        self.work_file_error = work_file_error
        self.note_error = note_error

    @property
    def id(self):
        return self.version["id"]

    @property
    def code(self):
        return self.version.get("code") or str(self.id)

    @property
    def url(self):
        return config.entity_url("Version", self.id)


# -- the service ------------------------------------------------------------

class PublishService:
    """Orchestrates a publish. One instance per dialog is fine; it is cheap."""

    def __init__(self, sg):
        self.sg = sg

    # -- preflight -------------------------------------------------------

    def preflight(self, request, policy=None, check_name=True):
        """Everything that must hold before ShotGrid is touched.

        Run by the dialog as the artist picks a file, and again here at the
        top of `publish()`. The second run is not redundant: the dialog may
        have been open for an hour, and files move, get overwritten and get
        unmounted. Client-side validation is a courtesy, not a guarantee.
        """
        return preflight.run(
            self.sg, request.project, request.task, request.name,
            request.media_path, policy=policy, check_name=check_name)

    # -- validation ------------------------------------------------------

    def validate_context(self, project, task):
        """Refuse early, and say which part of the context is missing."""
        if not project or not project.get("id"):
            raise ContextError("No project is open.")
        if not task or not task.get("id"):
            raise ContextError(
                "No task selected. Right-click a task in My Tasks and publish "
                "from there, so the Version lands on the right shot.")
        if not task.get("entity"):
            raise ContextError(
                f"Task '{task.get('content', '')}' is not linked to a shot or "
                f"asset, so a Version published against it would have nothing "
                f"to attach to.")
        return True

    def inspect_media(self, path):
        """MediaInfo, or a MediaError explaining why this file cannot go."""
        if not path:
            raise MediaError("Choose a movie or an image to publish.")
        if not os.path.isfile(path):
            raise MediaError(f"The media file no longer exists:\n{path}")
        if not config.media_kind(path):
            ext = os.path.splitext(path)[1] or "(no extension)"
            raise MediaError(
                f"{ext} is not a media format ShotDeck publishes.\n\n"
                f"Movies: {', '.join(sorted(config.MOVIE_EXTENSIONS))}\n"
                f"Images: {', '.join(sorted(config.IMAGE_EXTENSIONS))}")
        if not os.access(path, os.R_OK):
            raise MediaError(f"The media file cannot be read:\n{path}")

        info = media_inspector.inspect(path)
        if info.size == 0:
            raise MediaError(f"The media file is empty:\n{path}")
        return info

    # -- naming ----------------------------------------------------------

    def suggest_version_name(self, task, existing=None):
        """<entity>_<step>_v###, continuing from what the task already has."""
        if existing is None:
            try:
                existing = self.sg.versions_for_task(task["id"])
            except Exception as e:
                log.warning("could not list existing versions: %s", e)
                existing = []
        return next_version_name(task, existing)

    def check_name_available(self, project, task, name):
        """Raise if ShotGrid already has this Version name.

        Called both as the artist types (advisory) and again immediately before
        the create (authoritative), because two artists can reach v004 at the
        same moment.
        """
        if not name:
            raise PublishError("Give the version a name first.")
        try:
            clash = self.sg.version_exists(project, name, task["id"])
        except Exception as e:
            # A site that will not let us look is not a reason to block the
            # publish; the create itself is still the real gate.
            log.warning("could not check for an existing Version: %s", e)
            return None
        if clash:
            raise DuplicateVersionError(
                f"A Version named {name} already exists on this task.\n\n"
                f"Choose another version name — ShotDeck will not overwrite "
                f"an existing Version.", f"Version {clash['id']}")
        return None

    # -- the publish itself ----------------------------------------------

    def publish(self, request, on_stage=None, cancelled=None):
        """Create the Version, upload the media, register the work file.

        `on_stage(text)` is called before each step. `cancelled()` is polled
        between steps: cancelling before the create costs nothing, cancelling
        after it removes the half-made Version rather than leaving an empty one
        on the shot.
        """
        cancelled = cancelled or (lambda: False)
        started = time.time()

        def say(text):
            log.info(text)
            if on_stage:
                on_stage(text)

        def stop_if_cancelled(version=None):
            if not cancelled():
                return
            if version:
                self._cleanup(version)
            raise PublishCancelled(
                "Publish cancelled." + (" The part-made Version was removed."
                                        if version else ""))

        say("Running preflight…")
        report = self.preflight(request)
        _raise_for(report)
        if report.warnings and not request.accepted_warnings:
            # The dialog shows warnings and asks; a caller that skipped that
            # step does not get to publish past them by accident.
            raise WarningsNotAccepted(
                "This publish has warnings that were not confirmed:\n\n"
                + "\n\n".join(w.message for w in report.warnings))
        info = report.media_info

        task = request.task
        entity = (task.get("entity") or {})
        audit("start",
              task=task["id"], task_name=task.get("content", ""),
              entity=f"{entity.get('type', '?')}:{entity.get('id', '?')}",
              user=(self.sg.owner or {}).get("id", "unresolved"),
              api_identity=self.sg.api_identity,
              version_name=request.name, media=os.path.basename(info.path),
              size=info.size, kind=info.kind)

        stop_if_cancelled()

        say(f"Creating Version {request.name}…")
        try:
            version = self.sg.create_version(
                request.project, task, request.name, request.description,
                media_info=info)
        except Exception as e:
            audit("failed", stage="create", version_name=request.name,
                  reason=str(e))
            raise friendly(e, "creating the Version")
        audit("version_created", version=version["id"],
              version_name=request.name)

        stop_if_cancelled(version)

        say(f"Uploading {os.path.basename(info.path)} "
            f"({media_inspector.human_size(info.size)})…")
        upload_started = time.time()
        try:
            self.sg.upload_media(version["id"], info.path)
        except Exception as e:
            audit("failed", stage="upload", version=version["id"],
                  reason=str(e))
            self._cleanup(version)
            raise friendly(e, "uploading the media")
        audit("upload_finished", version=version["id"],
              seconds=round(time.time() - upload_started, 1))

        # Movies get a thumbnail out of transcoding; stills do not, and a
        # Version with no thumbnail is invisible in ShotGrid's list views.
        if info.kind != "movie":
            say("Uploading thumbnail…")
            try:
                self.sg.upload_version_thumbnail(version["id"], info.path)
            except Exception as e:
                log.warning("thumbnail upload skipped: %s", e)

        stop_if_cancelled(version)

        note = error = ""
        if request.work_file:
            say(f"Registering {os.path.basename(request.work_file)}…")
            try:
                note = self.sg.attach_work_file(
                    request.project, task, version, request.work_file)
            except Exception as e:
                # The Version and its media are already in ShotGrid: this is
                # worth reporting, not worth failing.
                log.warning("work file not registered: %s", e)
                error = str(e)

        note_error = ""
        if request.note:
            say("Posting note…")
            try:
                self.sg.create_note(request.project, version, request.note,
                                    task=task)
            except Exception as e:
                # Same reasoning as the work file: the Version is published,
                # and a note that did not post is worth saying, not worth
                # calling the publish failed.
                log.warning("publish note not posted: %s", e)
                note_error = str(e)

        elapsed = time.time() - started
        audit("finished", version=version["id"], version_name=request.name,
              seconds=round(elapsed, 1), work_file=bool(request.work_file),
              work_file_ok=not error)
        say("Done")
        return PublishResult(version, info, elapsed, note, error, note_error)

    def _cleanup(self, version):
        """Remove a Version that never got its media."""
        try:
            self.sg.delete_version(version["id"])
            audit("cleanup", version=version["id"], removed=True)
        except Exception as e:
            # Better a stray empty Version than a crash on top of a failure --
            # but say so, because someone will have to tidy it up.
            log.warning("could not remove Version %s after a failed publish: "
                        "%s", version["id"], e)
            audit("cleanup", version=version["id"], removed=False,
                  reason=str(e))


# -- helpers ----------------------------------------------------------------

def _raise_for(report):
    """Turn the first blocking finding into the right kind of PublishError."""
    if report.passed:
        return
    finding = report.errors[0]
    error_type = _FINDING_ERRORS.get(finding.code, PublishError)
    raise error_type(finding.message, finding.detail)


def next_version_name(task, existing):
    """The next <entity>_<step>_v### for this task.

    Numbering follows the highest v### already on the task rather than the
    count, so a deleted v003 does not hand v003 out twice.
    """
    import re

    entity = (task.get("entity") or {}).get("name") or "version"
    step = (task.get("step") or {}).get("name") or task.get("content") or ""
    stem = "_".join(p for p in (entity, step.replace(" ", "")) if p)

    highest = 0
    for v in existing or []:
        match = re.search(r"[._]v(\d+)\b", v.get("code") or "", re.IGNORECASE)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{stem}_v{highest + 1:03d}"


def audit(event, **fields):
    """One structured line per publish milestone.

    Deliberately key=value: a pipeline TD greps these out of the session log to
    reconstruct a failed publish. Credentials never appear here -- only the
    script *name* is ever passed in, never the key.
    """
    pairs = " ".join(f"{k}={_scrub(k, v)}" for k, v in fields.items())
    log.info("publish.%s %s", event, pairs)


_SECRET_HINTS = ("key", "secret", "token", "password", "passwd")


def _scrub(key, value):
    if any(hint in key.lower() for hint in _SECRET_HINTS):
        return "***"
    text = str(value)
    return f'"{text}"' if " " in text else text
