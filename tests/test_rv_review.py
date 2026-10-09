"""Notes from RV: which Version a source is, and the Note that goes up."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "rez", "flow_dcc", "startup", "rv"))

import config          # noqa: E402
import fakes           # noqa: E402
import flow_review     # noqa: E402
import rv_player       # noqa: E402

SHOT = {"type": "Shot", "id": 9, "name": "AD1030"}
TASK = {"type": "Task", "id": 77, "name": "Comp"}


def _review(**versions):
    return {"site": "https://x", "project": {"type": "Project", "id": 5},
            "login": "priya", "user": {"type": "HumanUser", "id": 43},
            "versions": [dict(v, code=code) for code, v in versions.items()]}


def test_a_source_finds_its_version_by_path_or_sequence():
    a = {"path": "/jobs/ad/AD1030_v001.%04d.exr", "id": 1}
    b = {"path": "/jobs/ad/AD1030_v002.mov", "id": 2}
    assert flow_review.version_for("/jobs/ad/AD1030_v002.mov", [a, b]) is b
    # RV may hand a sequence back in its own notation.
    assert flow_review.version_for(
        "/jobs/ad/AD1030_v001.1001-1100#.exr", [a, b]) is a
    assert flow_review.version_for("/elsewhere/x.mov", [a, b]) is None
    assert flow_review.version_for("/elsewhere/x.mov", [a]) is a, \
        "one version: it is that one"


def test_the_note_is_signed_linked_and_carries_the_frame():
    image = os.path.join(tempfile.mkdtemp(), "frame.png")
    with open(image, "wb") as f:
        f.write(b"png")
    review = _review(AD1030_v002={"path": "/a.mov", "id": 2,
                                  "entity": SHOT, "task": TASK})
    sg = fakes.FakeShotgun()

    note = flow_review.send(sg, review, review["versions"][0],
                            "Edge flickers here", 1012, image)
    data = [c for c in sg.calls if c[:2] == ("create", "Note")][0][2]
    assert data["content"] == "Priya: Edge flickers here"
    assert data["subject"] == "AD1030_v002 frame 1012"
    assert {"type": "Version", "id": 2} in data["note_links"]
    assert {"type": "Shot", "id": 9} in data["note_links"]
    assert data["tasks"] == [{"type": "Task", "id": 77}]
    assert "user" not in data, "the script writes it, signed by the lead"
    assert sg.uploads == [(note["id"], image, None)]


def test_rv_gets_the_menu_and_knows_which_version_is_which():
    saved = config.RV_EXECUTABLE, rv_player.reviewer
    config.RV_EXECUTABLE = "/opt/rv"
    rv_player.reviewer = {"login": "priya",
                          "user": {"type": "HumanUser", "id": 43}}
    try:
        _check_menu_and_review_env()
    finally:
        config.RV_EXECUTABLE, rv_player.reviewer = saved


def _check_menu_and_review_env():
    v = {"id": 2, "code": "AD1030_v002", "entity": SHOT, "sg_task": TASK}

    cmd = rv_player.command(["/a.mov"], notes=True)
    at = cmd.index("-pyeval")
    assert "flow_review.install()" in cmd[at + 1]
    compile(cmd[at + 1], "-pyeval", "exec")     # RV runs it as Python
    assert cmd[-1] == "/a.mov", "the media stays last"
    assert "-pyeval" not in rv_player.command(["/a.mov"])

    env = rv_player.review_env([v], ["/a.mov"], {"id": 5})
    review = json.loads(env["FLOW_RV_REVIEW"])
    assert review["login"] == "priya"
    assert review["versions"] == [{"path": "/a.mov", "id": 2,
                                   "code": "AD1030_v002", "entity": SHOT,
                                   "task": TASK}]
    assert flow_review.version_for("/a.mov", review["versions"])["id"] == 2
