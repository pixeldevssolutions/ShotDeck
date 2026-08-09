"""The parts of the UI that carry context: menus, the dialog, the browser.

Headless (QT_QPA_PLATFORM=offscreen, set by tests/run.py). Nothing here opens a
modal: `QMenu.exec` cannot be monkeypatched on a PySide class, and triggering
the publish action would open a real dialog and hang the run -- so the menu
building and the dialogs are driven directly instead.
"""

import os
import tempfile

from PySide6.QtCore import QThreadPool, QMimeData, QUrl, QPointF, Qt
from PySide6.QtGui import QPixmap, QColor, QDropEvent, QDragEnterEvent
from PySide6.QtWidgets import QApplication, QMenu

import config
import fakes
import publish_service

app = None
TMP = tempfile.mkdtemp(prefix="shotdeck-ui-")
PNG = os.path.join(TMP, "SH010_comp_v004.png")
NK = os.path.join(TMP, "SH010_comp_v004.nk")


def setup_module():
    global app
    app = QApplication.instance() or QApplication([])
    pm = QPixmap(400, 225)
    pm.fill(QColor("#3d9dff"))
    pm.save(PNG)
    with open(NK, "w") as f:
        f.write("# nuke script\n")


def settle(ms=4000):
    app.processEvents()
    QThreadPool.globalInstance().waitForDone(ms)
    for _ in range(8):
        app.processEvents()


# -- the task context menu -------------------------------------------------

def test_right_click_offers_publish_with_the_task_attached():
    from ui.software_page import TasksTable

    table = TasksTable()
    menu = QMenu()
    sub = table._add_publish_actions(menu, fakes.TASK)

    got = []
    table.publish_requested.connect(got.append)
    [a for a in sub.actions() if "Standalone" in a.text()][0].trigger()
    assert got and got[0]["id"] == fakes.TASK["id"], \
        "the publish must carry the task that was right-clicked"


def test_right_click_offers_view_versions():
    from ui.software_page import TasksTable

    table = TasksTable()
    menu = QMenu()
    sub = table._add_version_actions(menu, fakes.TASK)

    got = []
    table.versions_requested.connect(got.append)
    actions = [a for a in sub.actions() if "View Versions" in a.text()]
    assert actions, "Versions ▸ View Versions should be in the menu"
    actions[0].trigger()
    assert got and got[0]["id"] == fakes.TASK["id"]


def test_view_versions_is_disabled_without_an_entity():
    from ui.software_page import TasksTable

    table = TasksTable()
    menu = QMenu()          # held: a collected QMenu takes its submenu with it
    sub = table._add_version_actions(menu, fakes.TASK_NO_ENTITY)
    assert not sub.actions()[0].isEnabled()


# -- the publish dialog ----------------------------------------------------

def _dialog(sg=None):
    from ui.publish_dialog import PublishDialog
    client = fakes.client(sg)
    dialog = PublishDialog(client, fakes.PROJECT, fakes.TASK,
                           fakes.ARTIST["email"])
    # Shown even offscreen: a child widget of a hidden window reports
    # isVisible() False, and drops are only delivered to a shown widget.
    dialog.show()
    settle(500)
    return dialog


def test_dialog_shows_the_task_context_and_suggests_a_name():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v003")
    dialog = _dialog(sg)
    assert dialog.name_edit.text() == "SH010_Comp_v004"
    assert dialog.task["id"] == fakes.TASK["id"]
    assert not dialog.publish_btn.isEnabled(), "nothing chosen yet"


def test_drop_routes_media_and_scene_files():
    dialog = _dialog()
    _drop(dialog, [PNG, NK])
    # Compared per path element: a dropped URL comes back with forward slashes
    # even on Windows, which says nothing about the routing.
    assert _same(dialog.file_edit.text(), PNG)
    assert _same(dialog.work_edit.text(), NK)
    assert dialog.publish_btn.isEnabled()


def test_dropping_an_unsupported_file_blocks_the_publish():
    dialog = _dialog()
    txt = os.path.join(TMP, "notes.txt")
    open(txt, "w").write("hello")
    _drop(dialog, [txt])
    assert not dialog.publish_btn.isEnabled()
    assert "not a publishable media format" in dialog.file_info.text()


def test_duplicate_name_warns_and_blocks_before_any_upload():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v004")
    dialog = _dialog(sg)
    dialog.file_edit.setText(PNG)
    dialog.name_edit.setText("SH010_Comp_v004")
    dialog._check_name()
    settle(500)
    assert dialog.name_warning.isVisible()
    assert "already exists" in dialog.name_warning.text()
    assert not dialog.publish_btn.isEnabled()
    assert not sg.uploads


def test_media_is_inspected_off_the_ui_thread():
    dialog = _dialog()
    _choose(dialog, PNG)
    assert dialog.media_info is not None
    assert "400 × 225" in dialog.file_info.text()


def test_preflight_reports_before_anything_is_created():
    sg = fakes.FakeShotgun()
    dialog = _dialog(sg)
    _choose(dialog, PNG)
    assert dialog.report is not None
    assert not any(c[0] == "create" for c in sg.calls), \
        "the preflight must not create anything"
    text = _labels(dialog.preflight_panel)
    assert "Project: UAT6" in text
    assert "Version name available" in text


def test_a_warning_must_be_accepted_before_publish_is_offered():
    """The fixtures live in the OS temp directory, which is exactly the case
    the path policy exists for."""
    dialog = _dialog()
    dialog.file_edit.setText(PNG)
    dialog._run_preflight()
    settle()
    assert dialog.report.warnings
    assert dialog.accept_warnings.isVisible()
    assert not dialog.publish_btn.isEnabled(), \
        "a warning must not be publishable until it is acknowledged"

    dialog.accept_warnings.setChecked(True)
    assert dialog.publish_btn.isEnabled()


def test_an_error_cannot_be_ticked_past():
    dialog = _dialog()
    txt = os.path.join(TMP, "notes.txt")
    open(txt, "w").write("hello")
    dialog.file_edit.setText(txt)
    dialog._run_preflight()
    settle()
    assert not dialog.report.passed
    assert not dialog.accept_warnings.isVisible(), \
        "there is no continuing past an error"
    assert not dialog.publish_btn.isEnabled()


def test_media_from_another_project_is_refused_in_the_dialog():
    dialog = _dialog()
    dialog.file_edit.setText("/jobs/SHOW002/renders/v001.mov")
    dialog._run_preflight()
    settle()
    assert not dialog.publish_btn.isEnabled()


def test_publish_shows_a_result_with_the_api_identity():
    sg = fakes.FakeShotgun()
    dialog = _dialog(sg)
    _choose(dialog, PNG)
    dialog._publish()
    settle()

    assert dialog.published is not None
    assert sg.uploads, "the media should have been uploaded"
    assert dialog.pages.currentWidget() is dialog.result_page
    labels = _labels(dialog.result_page)
    assert config.SG_SCRIPT_NAME in labels
    assert fakes.ARTIST["email"] in labels
    assert "Publish Successful" in dialog.result_page.heading.text()


def test_failed_publish_keeps_the_dialog_open_and_says_why():
    sg = fakes.FakeShotgun()
    sg.fail_create = RuntimeError("CRUD ERROR: Create on Version not permitted")
    dialog = _dialog(sg)
    dialog.file_edit.setText(PNG)
    settle()
    # The message box would block, so the handler is driven directly with the
    # error the service produces.
    dialog._on_failed(publish_service.friendly(sg.fail_create))
    assert dialog.published is None
    assert "permission" in dialog.status.text().lower()


def test_cancel_during_a_publish_asks_the_job_to_stop():
    dialog = _dialog()
    dialog.file_edit.setText(PNG)
    settle()

    class Job:
        cancelled = False

        def cancel(self):
            Job.cancelled = True

    dialog._job = Job()
    dialog._on_cancel()
    assert Job.cancelled
    assert "Cancelling" in dialog.status.text()


# -- the version browser ---------------------------------------------------

def _browser(sg):
    from ui.version_browser import VersionBrowser
    browser = VersionBrowser(fakes.client(sg), fakes.PROJECT, fakes.TASK)
    browser.show()
    settle()
    return browser


def test_browser_lists_versions_newest_first():
    sg = fakes.FakeShotgun()
    for i in range(1, 4):
        sg.add_version(f"SH010_Comp_v00{i}")
    browser = _browser(sg)
    assert browser.table.rowCount() == 3
    assert browser.table.item(0, 0).text() == "SH010_Comp_v003"
    assert "3 versions" in browser.count_lbl.text()


def test_browser_shows_department_user_status_and_date():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v001",
                   **{"sg_task.Task.step": {"type": "Step", "id": 9,
                                            "name": "Comp"}})
    browser = _browser(sg)
    row = [browser.table.item(0, c).text() for c in range(5)]
    assert row[0] == "SH010_Comp_v001"
    assert row[1] == "Comp"
    assert row[2] == "Jitesh"
    assert row[3] == "rev"
    assert row[4]


def test_browser_filters_are_sent_to_shotgrid():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v001", sg_status_list="apr")
    sg.add_version("SH010_Comp_v002", sg_status_list="wip")
    browser = _browser(sg)

    browser.status.setCurrentIndex(
        [browser.status.itemData(i)
         for i in range(browser.status.count())].index("apr"))
    settle()
    assert browser.table.rowCount() == 1
    assert browser.table.item(0, 0).text() == "SH010_Comp_v001"

    find = [c for c in sg.calls if c[0] == "find" and c[1] == "Version"][-1]
    assert ["sg_status_list", "is", "apr"] in find[2], \
        "the status filter must be a query, not a pass over the rows"


def test_browser_search_is_debounced_then_queried():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v001", description="client notes")
    sg.add_version("SH010_Roto_v001", description="paint pass")
    browser = _browser(sg)
    before = len([c for c in sg.calls if c[0] == "find"])

    browser.search.setText("Roto")
    app.processEvents()
    assert len([c for c in sg.calls if c[0] == "find"]) == before, \
        "typing should not query on every keystroke"

    browser._search_timer.timeout.emit()      # the debounce firing
    settle()
    assert browser.table.rowCount() == 1
    assert browser.table.item(0, 0).text() == "SH010_Roto_v001"


def test_browser_scope_can_narrow_to_the_task():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v001")
    sg.add_version("SH010_Light_v001",
                   sg_task={"type": "Task", "id": 999})
    browser = _browser(sg)
    assert browser.table.rowCount() == 2

    browser.scope.setCurrentIndex(1)          # this task only
    settle()
    assert browser.table.rowCount() == 1
    assert browser.table.item(0, 0).text() == "SH010_Comp_v001"


def test_browser_pages_rather_than_loading_everything():
    sg = fakes.FakeShotgun()
    for i in range(1, 8):
        sg.add_version(f"SH010_Comp_v00{i}")
    old = config.VERSION_PAGE_SIZE
    config.VERSION_PAGE_SIZE = 3
    try:
        browser = _browser(sg)
        assert browser.table.rowCount() == 3
        assert browser.more_btn.isVisible()
        browser._load_more()
        settle()
        assert browser.table.rowCount() == 6
    finally:
        config.VERSION_PAGE_SIZE = old


def test_browser_details_only_show_fields_the_site_filled_in():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v001", description="Final comp with notes",
                   frame_range="1001-1120")
    browser = _browser(sg)
    browser.table.selectRow(0)
    settle()
    text = _labels(browser)
    assert "Final comp with notes" in text
    assert "1001-1120" in text
    assert "Media path" not in text, \
        "a field this version does not have should not be shown"


def test_browser_survives_a_failed_query():
    sg = fakes.FakeShotgun()
    sg.fail_find = RuntimeError("Permission denied on Version")
    browser = _browser(sg)
    assert browser.stack.currentWidget() is browser.empty
    assert "Permission denied" in browser.count_lbl.text()
    assert not browser.more_btn.isVisible()


def test_browser_empty_state_when_nothing_matches():
    browser = _browser(fakes.FakeShotgun())
    assert browser.stack.currentWidget() is browser.empty
    assert browser.count_lbl.text() in ("", "0 versions")


# -- notes in the browser --------------------------------------------------

def _browser_with_notes():
    sg = fakes.FakeShotgun()
    version = sg.add_version("SH010_Comp_v004")
    note = sg.add_note(version["id"], "Reduce brightness.",
                       user=fakes.CLIENT)
    sg.add_reply(note["id"], "Can Comp investigate?", user=fakes.PRODUCER)
    sg.add_reply(note["id"], "Updated in v005.", user=fakes.ARTIST)
    browser = _browser(sg)
    browser.tabs.setCurrentIndex(1)          # Notes
    browser.table.selectRow(0)
    settle()
    return sg, browser


def test_notes_show_for_the_selected_version_with_their_authors():
    sg, browser = _browser_with_notes()
    text = _labels(browser.notes)
    assert "Reduce brightness." in text
    assert "Sam" in text and "CLIENT" in text
    assert "Can Comp investigate?" in text
    assert "Updated in v005." in text


def test_replies_are_drawn_under_their_note():
    from ui.notes_panel import MessageCard

    sg, browser = _browser_with_notes()
    cards = browser.notes.findChildren(MessageCard)
    kinds = [c.message.kind for c in cards]
    assert kinds == ["note", "reply", "reply"]
    assert all(c.message.depth == 1 for c in cards if c.message.kind == "reply")


def test_edit_and_delete_only_appear_on_your_own_messages():
    from PySide6.QtWidgets import QPushButton
    from ui.notes_panel import MessageCard

    sg, browser = _browser_with_notes()
    cards = browser.notes.findChildren(MessageCard)
    buttons = {c.message.author_name:
               [b.text() for b in c.findChildren(QPushButton)]
               for c in cards}
    assert "Delete" not in buttons["Sam"], "the client's note is not ours"
    assert "Delete" in buttons["Jitesh"], "our own reply is"


def test_posting_a_note_writes_to_shotgrid_and_reloads_notes_only():
    sg, browser = _browser_with_notes()
    version_queries = len([c for c in sg.calls
                           if c[0] == "find" and c[1] == "Version"])

    browser.notes.compose.setPlainText("Grade updated.")
    browser.notes._post()
    settle()

    created = [c for c in sg.calls if c[0] == "create" and c[1] == "Note"]
    assert created and created[0][2]["content"] == "Grade updated."
    assert "Grade updated." in _labels(browser.notes)
    assert len([c for c in sg.calls
                if c[0] == "find" and c[1] == "Version"]) == version_queries, \
        "refreshing notes must not re-query the version list"


def test_replying_from_the_card_creates_a_reply():
    sg, browser = _browser_with_notes()
    thread = browser.notes.threads[0]
    browser.notes._start_reply(thread)
    browser.notes.compose.setPlainText("On it.")
    browser.notes._post()
    settle()
    assert sg.replies[-1]["content"] == "On it."
    assert sg.replies[-1]["entity"]["id"] == thread.id


def test_the_activity_tab_merges_notes_and_the_publish():
    sg, browser = _browser_with_notes()
    browser.tabs.setCurrentIndex(2)          # Activity
    settle()
    text = _labels(browser.activity)
    assert "published SH010_Comp_v004" in text
    assert "wrote:" in text and "replied:" in text


def test_notes_failure_is_reported_in_place():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v004")
    browser = _browser(sg)
    browser.table.selectRow(0)
    settle()

    sg.fail_find = RuntimeError("Permission denied on Note")
    browser.notes._cooldown.stop()
    browser.notes.refresh()
    settle()
    assert "Notes unavailable" in browser.notes.status.text()


# -- helpers ---------------------------------------------------------------

def _drop(widget, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    enter = QDragEnterEvent(widget.rect().center(), Qt.CopyAction, mime,
                            Qt.LeftButton, Qt.NoModifier)
    app.sendEvent(widget, enter)
    app.sendEvent(widget, QDropEvent(QPointF(widget.rect().center()),
                                     Qt.CopyAction, mime, Qt.LeftButton,
                                     Qt.NoModifier))
    app.processEvents()


def _choose(dialog, path):
    """Pick a file, run the preflight now rather than after the debounce, and
    accept the temp-directory warning the fixtures inevitably raise."""
    dialog.file_edit.setText(path)
    dialog._run_preflight()
    settle()
    if dialog.accept_warnings.isVisible():
        dialog.accept_warnings.setChecked(True)
    return dialog.report


def _same(a, b):
    return os.path.normcase(os.path.normpath(a)) == \
        os.path.normcase(os.path.normpath(b))


def _labels(widget):
    from PySide6.QtWidgets import QLabel
    return "\n".join(l.text() for l in widget.findChildren(QLabel))
