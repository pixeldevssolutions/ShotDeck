"""Review notes from inside OpenRV: draw on a frame, send it to ShotGrid.

OpenRV ships without the ShotGrid integration commercial RV has, so a lead's
annotations would otherwise never leave RV. rv_player starts RV with a
-pyeval that puts this folder on sys.path and calls install(); the menu it
adds is

    Flow > Send Note to ShotGrid...

which takes the frame on screen, annotations and all, asks for the note text,
and creates a Note on the source's Version -- linked to its shot and task,
signed "Jitesh: ..." like every note Flow writes -- with the frame attached.

What RV does not know, rv_player tells it in FLOW_RV_REVIEW (JSON): which
Version each source path is, who is reviewing, and the site. Only install()
and the menu callback touch RV; the rest is plain Python, tested without it.
"""

import json
import os
import re
import tempfile

REVIEW_VAR = "FLOW_RV_REVIEW"
SCRIPT_DEFAULT = "SG_daemon"

# The frame part of a sequence path and everything after it: RV may hand back
# file.1001-1100#.exr for the file.%04d.exr it was given.
_FRAMES = re.compile(r"[.\-_]?(%0?\d*d|\d*-?\d*[#@]+).*$")

_mode = None        # the live MinorMode; kept so it is never collected


def payload(environ=None):
    """The review context rv_player exported, or {} outside a Flow launch."""
    try:
        return json.loads((environ or os.environ).get(REVIEW_VAR) or "{}")
    except ValueError:
        return {}


def _stem(path):
    path = os.path.normpath(path or "")
    return os.path.join(os.path.dirname(path),
                        _FRAMES.sub("", os.path.basename(path)))


def version_for(media, versions):
    """The Version a source came from: same path, same sequence, or the only one."""
    for v in versions:
        if os.path.normpath(v["path"]) == os.path.normpath(media or ""):
            return v
    for v in versions:
        if _stem(v["path"]) == _stem(media):
            return v
    return versions[0] if len(versions) == 1 else None


def sign(content, login):
    """Same as notes_service.sign in the app: "Jitesh: " in front, once."""
    if not login:
        return content
    name = login[:1].upper() + login[1:]
    if content.lower().startswith(name.lower() + ":"):
        return content
    return "%s: %s" % (name, content)


def note_data(review, version, text, frame):
    """The Note for this Version, shaped like SGClient.create_note's."""
    links = [{"type": "Version", "id": version["id"]}]
    entity = version.get("entity")
    if entity:
        links.append({"type": entity["type"], "id": entity["id"]})
    data = {
        "project": {"type": "Project", "id": review["project"]["id"]},
        "subject": "%s frame %s" % (version.get("code") or "", frame),
        "content": sign(text, review.get("login")),
        "note_links": links,
    }
    task = version.get("task")
    if task:
        data["tasks"] = [{"type": "Task", "id": task["id"]}]
    # No "user": the Note is the script's, the lead is the signature.
    return data


def send(sg, review, version, text, frame, image=None):
    """Create the Note and attach the frame. Returns the Note."""
    note = sg.create("Note", note_data(review, version, text, frame))
    if image and os.path.isfile(image):
        sg.upload("Note", note["id"], image)
    return note


def connect(review):
    """A ShotGrid connection, with the API Flow pointed RV at."""
    from flow_dcc import shotgrid
    api = shotgrid.api()
    if api is None:
        raise RuntimeError("shotgun_api3 is not importable inside RV (%s=%r)."
                           % (shotgrid.API_PATH_VAR,
                              os.environ.get(shotgrid.API_PATH_VAR)))
    key = os.environ.get(shotgrid.KEY_VAR)
    if not key:
        raise RuntimeError("%s is not set in this RV session." % shotgrid.KEY_VAR)
    return api.Shotgun(review["site"],
                       script_name=os.environ.get(shotgrid.SCRIPT_VAR)
                       or SCRIPT_DEFAULT,
                       api_key=key)


# -- RV ---------------------------------------------------------------------

def install():
    """Add the Flow menu. Called from rv_player's -pyeval."""
    global _mode
    from rv import commands, rvtypes

    class FlowReview(rvtypes.MinorMode):
        def __init__(self):
            rvtypes.MinorMode.__init__(self)
            self.init("flow-review", None, None,
                      [("Flow", [("Send Note to ShotGrid...", send_from_rv,
                                  None, lambda: commands.NeutralMenuState)])])

    _mode = FlowReview()
    _mode.toggle()


def _grab_frame(path):
    """The frame as shown, annotations included, written to path."""
    from rv import commands, qtutils
    try:
        commands.exportCurrentFrame(path)
    except Exception:
        pass
    if not os.path.isfile(path):
        # ponytail: the GL view as a fallback -- also catches RV's own HUD if
        # one is showing; drop it once exportCurrentFrame is confirmed on 3.1.
        qtutils.sessionGLView().grabFramebuffer().save(path)
    return path if os.path.isfile(path) else None


def send_from_rv(event=None):
    from rv import commands, qtutils
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide2 import QtWidgets
    parent = qtutils.sessionWindow()
    review = payload()

    frame = commands.frame()
    # ponytail: the top source at this frame; a wipe or tile notes the first
    # one -- add a picker if leads need to note the one underneath.
    sources = commands.sourcesAtFrame(frame)
    media = ""
    if sources:
        media = commands.getStringProperty(sources[0] + ".media.movie")[0]
    version = version_for(media, review.get("versions") or [])
    if not version:
        QtWidgets.QMessageBox.warning(
            parent, "Flow",
            "This source was not opened from a ShotGrid Version in Flow, so "
            "there is no Version to put the note on.")
        return

    text, ok = QtWidgets.QInputDialog.getMultiLineText(
        parent, "Send Note to ShotGrid",
        "%s, frame %s\nThe frame on screen, with your annotations, is "
        "attached." % (version.get("code"), frame))
    if not ok or not text.strip():
        return

    image = _grab_frame(os.path.join(
        tempfile.gettempdir(), "flow_note_%s_%s.png" % (version["id"], frame)))
    try:
        send(connect(review), review, version, text.strip(), frame, image)
    except Exception as e:
        QtWidgets.QMessageBox.critical(
            parent, "Flow", "The note was not sent to ShotGrid:\n\n%s" % e)
        return
    commands.displayFeedback("Note sent to ShotGrid on %s"
                             % version.get("code"), 4.0)
