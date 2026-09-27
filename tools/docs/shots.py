"""Render Flow's screens to PNGs for the user manual.

Runs headless (Qt's offscreen platform) against tests/fakes.py, so it needs
neither a display nor a ShotGrid site. Each function returns the file name it
wrote; make_manual.py embeds them.
"""

import os
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

# Deliberately NOT the offscreen platform: it ships no font database on
# Windows, so every label grabs as tofu boxes. The real platform plugin is
# used instead and WA_DontShowOnScreen keeps the windows off the desktop.
os.environ.setdefault("SG_SCRIPT_KEY", "test-key-not-real")
os.environ.setdefault("FLOW_LOG_DIR",
                      os.path.join(tempfile.gettempdir(), "flow-docs-logs"))

if "shotgun_api3" not in sys.modules:
    try:
        import shotgun_api3          # noqa: F401
    except ImportError:
        sys.modules["shotgun_api3"] = types.ModuleType("shotgun_api3")

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu

import fakes

OUT = os.path.join(HERE, "images")
app = None


def settle(ms=4000):
    app.processEvents()
    QThreadPool.globalInstance().waitForDone(ms)
    for _ in range(8):
        app.processEvents()


def make_frame(path, colour, x):
    """A stand-in plate: a flat sky with a box that moves between versions."""
    pm = QPixmap(640, 360)
    pm.fill(QColor(colour))
    painter = QPainter(pm)
    painter.fillRect(x, 150, 180, 120, QColor("#e8c47a"))
    painter.end()
    pm.save(path)


def pump(seconds):
    """Keep the event loop turning; debounced work needs wall-clock time."""
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shot(widget, name, w=1080, h=720, wait=0.0):
    """Grab one widget to images/<name>.png and return the file name."""
    from ui.widgets import STYLE
    widget.setStyleSheet(STYLE)          # MainWindow applies this in the app
    widget.setAttribute(Qt.WA_DontShowOnScreen, True)
    widget.resize(w, h)
    widget.show()
    settle()
    if wait:
        pump(wait)
    path = os.path.join(OUT, name + ".png")
    widget.grab().save(path)
    widget.hide()
    return os.path.basename(path)


# -- the data every screen is built on ------------------------------------

SOFTWARE = [
    {"code": "Maya", "version": "2024"},
    {"code": "Nuke", "version": "15.0"},
    {"code": "Houdini", "version": "20.0"},
    {"code": "Blender", "version": "4.2"},
    {"code": "Silhouette", "version": "2024"},
    {"code": "3DEqualizer", "version": "r7"},
]

TASKS = [
    dict(fakes.TASK, id=7701, content="Compositing", sg_status_list="ip",
         entity=dict(fakes.SHOT, name="SH010"),
         step={"type": "Step", "id": 9, "name": "Comp"},
         **{"entity.Shot.sg_sequence": {"type": "Sequence", "name": "SEQ001"}},
         due_date="2026-10-02"),
    dict(fakes.TASK, id=7702, content="Lighting", sg_status_list="rdy",
         entity=dict(fakes.SHOT, name="SH020"),
         step={"type": "Step", "id": 10, "name": "Light"},
         **{"entity.Shot.sg_sequence": {"type": "Sequence", "name": "SEQ001"}},
         due_date="2026-10-06"),
    dict(fakes.TASK, id=7703, content="Animation", sg_status_list="fin",
         entity=dict(fakes.SHOT, name="SH030"),
         step={"type": "Step", "id": 12, "name": "Anim"},
         **{"entity.Shot.sg_sequence": {"type": "Sequence", "name": "SEQ002"}},
         due_date="2026-09-29"),
]

PROJECTS = [
    {"id": 1213, "name": "UAT6", "tank_name": "UAT6"},
    {"id": 1214, "name": "Nightfall", "tank_name": "nightfall"},
    {"id": 1215, "name": "Harbour Lights", "tank_name": "harbour"},
]

STATUSES = [("wip", "In Progress"), ("rev", "Pending Review"),
            ("apr", "Approved")]

NOTES = ["Push the key light a stop hotter.",
         "Edge matte is chattering on frames 1012-1030.",
         "Grade looks good — approved for the cut."]


FRAMES = []          # filled by all_shots(); one rendered still per version


def seeded_client():
    sg = fakes.FakeShotgun()
    for n, code in enumerate(["SH010_comp_v001", "SH010_comp_v002",
                              "SH010_comp_v003"]):
        v = sg.add_version(code, description="Grade pass %d" % (n + 1),
                           sg_status_list=["apr", "rev", "rev"][n],
                           sg_path_to_frames=FRAMES[n] if FRAMES else "")
        sg.add_note(v["id"], NOTES[n], user=fakes.PRODUCER,
                    subject=["Lighting", "Comp", "Grade"][n])
    return fakes.client(sg), sg


# -- the screens -----------------------------------------------------------

def splash():
    from ui.branding import Splash
    s = Splash("Loading Pipeline")
    s.set_message("Connecting to ShotGrid")
    # The splash draws itself against its own clock: the wordmark and the
    # status line only appear part-way through, so grab it after that.
    return shot(s, "01-splash", 1080, 720, wait=3.0)


def login():
    import auth.config as auth_config
    from auth.login_dialog import LoginDialog
    d = LoginDialog(auth_config.load())
    return shot(d, "02-login", 420, 260)


def projects():
    from ui.project_page import ProjectPage
    p = ProjectPage()
    p.set_projects(PROJECTS)
    return shot(p, "03-projects", 1080, 420)


def apps_tab():
    from ui.software_page import SoftwarePage
    page = SoftwarePage()
    page.set_project(fakes.PROJECT)
    page.set_software(SOFTWARE)
    page.set_tasks(TASKS)
    page.tabs.setCurrentIndex(0)
    return shot(page, "04-apps", 1080, 560)


def tasks_tab():
    from ui.software_page import SoftwarePage
    page = SoftwarePage()
    page.set_project(fakes.PROJECT)
    page.set_software(SOFTWARE)
    page.set_tasks(TASKS)
    page.set_statuses(STATUSES)
    page.tabs.setCurrentIndex(1)
    return shot(page, "05-tasks", 1080, 420)


def task_menu():
    from ui.software_page import TasksTable
    table = TasksTable()
    table.set_project(fakes.PROJECT)
    table.set_tasks(TASKS)
    table.set_statuses(STATUSES)
    table._packages = [("maya", ["2024", "2023"]), ("nuke", ["15.0"]),
                       ("houdini", ["20.0"])]

    # The same menu _on_context_menu builds, minus its blocking exec().
    task = TASKS[0]
    menu = QMenu()
    header = menu.addAction("Open SH010 with…")
    header.setEnabled(False)
    menu.addSeparator()
    table._add_publish_actions(menu, task)
    table._add_latest_version_actions(menu, task)
    table._add_version_actions(menu, task)
    menu.addSeparator()
    table._add_status_actions(menu, task)
    menu.addSeparator()
    table._add_folder_actions(menu, task)
    menu.addSeparator()
    for package, versions in table._packages:
        label = package.title()
        if len(versions) == 1:
            menu.addAction("{0}  {1}".format(label, versions[0]))
            continue
        sub = QMenu(label, menu)
        menu.addMenu(sub)
        for i, version in enumerate(versions):
            sub.addAction(version + ("   (latest)" if i == 0 else ""))

    from ui.widgets import STYLE
    menu.setStyleSheet(STYLE)
    menu.setAttribute(Qt.WA_DontShowOnScreen, True)
    menu.show()
    settle()
    path = os.path.join(OUT, "06-task-menu.png")
    menu.grab().save(path)
    menu.hide()
    return os.path.basename(path)


def review():
    from ui.review_page import ReviewPage
    client, _ = seeded_client()
    page = ReviewPage(client)
    page.set_project(fakes.PROJECT)
    page.refresh()
    settle()
    return shot(page, "07-needs-attention", 1080, 480)


def publish_dialog(frame):
    from ui.publish_dialog import PublishDialog
    client, _ = seeded_client()
    d = PublishDialog(client, fakes.PROJECT, fakes.TASK, fakes.ARTIST["email"])
    settle()
    return shot(d, "08-publish", 760, 640)


def publish_filled(frame):
    from ui.publish_dialog import PublishDialog
    client, _ = seeded_client()
    d = PublishDialog(client, fakes.PROJECT, fakes.TASK, fakes.ARTIST["email"])
    d.accept_file(frame)                 # what a drop onto the zone does
    d.desc_edit.setPlainText("Second grade pass, warmer key.")
    pump(2.5)                            # the preflight runs on a debounce
    settle()
    # Cosmetic only: show a path an artist would recognise instead of this
    # machine's. Signals are blocked so the preflight above is not re-run.
    d.file_edit.blockSignals(True)
    d.file_edit.setText("/home/jitesh/Desktop/SH010_comp_v004.png")
    d.file_edit.blockSignals(False)
    return shot(d, "08b-publish-filled", 760, 640)


def version_browser(frame):
    from ui.version_browser import VersionBrowser
    client, _ = seeded_client()
    d = VersionBrowser(client, fakes.PROJECT, fakes.TASK)
    settle()
    d.table.selectRow(0)                 # so Details/Notes have something in
    settle()
    return shot(d, "09-version-browser", 1080, 700)


def version_compare(frame):
    from ui.version_compare import VersionCompare
    client, sg = seeded_client()
    a, b = sg.versions[-2], sg.versions[-1]
    d = VersionCompare(client, fakes.PROJECT, a, b, versions=sg.versions)
    settle()
    return shot(d, "10-version-compare", 1080, 700)


def compare_wipe(frame):
    from ui.version_compare import VersionCompare
    client, sg = seeded_client()
    a, b = sg.versions[-2], sg.versions[-1]
    d = VersionCompare(client, fakes.PROJECT, a, b, versions=sg.versions)
    settle()
    for btn in d.findChildren(type(d.fit_btn)):
        if btn.text() == "Wipe":
            btn.click()
    settle()
    return shot(d, "10b-compare-wipe", 1080, 700)


def notes(frame):
    """The Notes tab as artists actually meet it: inside the version browser.

    NotesPanel on its own leaves its "select a version" placeholder showing,
    because the browser is what hides it."""
    from ui.version_browser import VersionBrowser
    client, sg = seeded_client()
    sg.add_reply(sg.notes[-1]["id"], "Fixed in v004 — re-rendering now.",
                 user=fakes.ARTIST)
    d = VersionBrowser(client, fakes.PROJECT, fakes.TASK)
    settle()
    d.table.selectRow(0)
    d.tabs.setCurrentIndex(1)            # Notes
    pump(1.5)
    settle()
    return shot(d, "11-notes", 1080, 860)


def console():
    """The Terminal pane, following a launch log the way it does in the app."""
    from ui.console import ConsolePanel
    log_path = os.path.join(OUT, "_launch.log")
    with open(log_path, "w") as f:
        f.write("\n".join([
            "# Flow launch  UAT6 / SH010 / Compositing",
            "# rez env maya-2024 flow_context -- maya",
            "resolved: maya-2024  flow_context-1.0.0",
            "FLOW_PROJECT=UAT6  FLOW_PROJECT_ID=1213  FLOW_TASK=7631",
            "FLOW_ENTITY=SH010  FLOW_STEP=Comp",
            "PYTHONPATH=/software/pipeline/Flow/rez/flow_dcc:...",
            "Maya 2024 started (pid 48213)",
            "flow_dcc: 5and8 menu installed",
        ]) + "\n")
    c = ConsolePanel()
    c.tail(log_path)
    return shot(c, "12-terminal", 1080, 260, wait=1.5)


STEPS = [
    ("splash", splash, ()),
    ("login", login, ()),
    ("projects", projects, ()),
    ("apps", apps_tab, ()),
    ("tasks", tasks_tab, ()),
    ("task_menu", task_menu, ()),
    ("review", review, ()),
    ("publish", publish_dialog, ("frame",)),
    ("publish_filled", publish_filled, ("frame",)),
    ("browser", version_browser, ("frame",)),
    ("compare", version_compare, ("frame",)),
    ("compare_wipe", compare_wipe, ("frame",)),
    ("notes", notes, ("frame",)),
    ("console", console, ()),
]


def all_shots():
    global app
    app = QApplication.instance() or QApplication([])
    os.makedirs(OUT, exist_ok=True)

    frame = os.path.join(OUT, "SH010_comp_v004.png")
    make_frame(frame, "#2f5d8c", 120)
    del FRAMES[:]
    for n in range(3):
        path = os.path.join(OUT, "_frame_v%03d.png" % (n + 1))
        # Each still differs a little, so Wipe and Difference have something
        # real to show rather than two identical panes.
        make_frame(path, ["#24425f", "#2f5d8c", "#3d7cb8"][n], 90 + n * 40)
        FRAMES.append(path)

    made = {}
    for key, fn, args in STEPS:
        args = tuple(frame if a == "frame" else a for a in args)
        try:
            made[key] = fn(*args)
            print("ok   ", key, made[key])
        except Exception as e:
            print("SKIP ", key, type(e).__name__, e)
    return made


if __name__ == "__main__":
    all_shots()
