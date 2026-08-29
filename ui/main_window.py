import getpass

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QMenu, QPushButton, QStackedWidget, QMessageBox, QSplitter,
)

import applog, config, launcher, paths, rv_player
from . import jobs
from .widgets import STYLE, UserChip
from .console import ConsolePanel
from .project_page import ProjectPage
from .publish_dialog import PublishDialog
from .review_page import ReviewPage
from .software_page import SoftwarePage
from .task_search import TaskSearch
from .version_browser import VersionBrowser
from .version_compare import VersionCompare

log = applog.get()


class MainWindow(QMainWindow):
    def __init__(self, sg, login=None, auth_result=None):
        super().__init__()
        self.sg = sg
        # login comes from auth.authenticate() in main(); the getpass fallback
        # keeps the window constructible in tests and from a shell.
        self.auth = auth_result
        self.login = login or (auth_result.login if auth_result else None) \
            or getpass.getuser()
        self.email = config.current_user_email(self.login)
        self.display_name = (auth_result.display_name if auth_result
                             else None) or self.login
        self.owner = None         # ShotGrid HumanUser, filled by _bootstrap
        self._projects = []       # full Project dicts, for the header search
        self._pending_task_id = None    # task to select once its project loads
        self.project = None
        self.task = None          # Task an app will be launched against
        self.pool = QThreadPool.globalInstance()
        self._jobs = set()        # in-flight workers, see _run()

        self.setWindowTitle(config.APP_TITLE)
        self.resize(1080, 720)
        self.setMinimumSize(760, 480)
        self.setStyleSheet(STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(54)
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(4)

        self.back_btn = QPushButton("\u2039  Projects")
        self.back_btn.setObjectName("backBtn")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.show_projects)
        self.back_btn.hide()
        h.addWidget(self.back_btn)

        # Breadcrumb: app name, then the project once one is open.
        self.title = QLabel(config.APP_TITLE)
        self.title.setObjectName("headerTitle")
        h.addWidget(self.title)

        self.crumb = QLabel("\u203a")
        self.crumb.setObjectName("crumb")
        self.crumb.hide()
        h.addWidget(self.crumb)

        self.crumb_project = QLabel("")
        self.crumb_project.setObjectName("headerTitle")
        self.crumb_project.hide()
        h.addWidget(self.crumb_project)

        h.addStretch()

        # Find a task without remembering which show it is on.
        self.task_search = TaskSearch()
        self.task_search.tasks_needed.connect(self._load_all_tasks)
        self.task_search.task_chosen.connect(self.goto_task)
        h.addWidget(self.task_search)

        # Needs Attention sits in the header rather than in a tab: it is a
        # different question from "what are my tasks", and the artist has to
        # be able to see the count without going looking for it.
        self.review_btn = QPushButton("Needs Attention")
        self.review_btn.setObjectName("termBtn")
        self.review_btn.setCheckable(True)
        self.review_btn.setCursor(Qt.PointingHandCursor)
        self.review_btn.setToolTip(
            "Notes on your versions, replies to your notes, and versions a "
            "supervisor pushed back")
        self.review_btn.toggled.connect(self.show_review)
        h.addWidget(self.review_btn)

        self.term_btn = QPushButton("Terminal")
        self.term_btn.setObjectName("termBtn")
        self.term_btn.setCheckable(True)
        self.term_btn.setCursor(Qt.PointingHandCursor)
        self.term_btn.setToolTip(
            "Show what Flow is running in the background (Ctrl+`)")
        self.term_btn.toggled.connect(self.toggle_console)
        h.addWidget(self.term_btn)

        h.addWidget(self._build_user_chip())
        root.addWidget(header)

        # pages, with the terminal as a collapsible bottom pane
        self.stack = QStackedWidget()
        self.project_page = ProjectPage()
        self.software_page = SoftwarePage()
        self.review_page = ReviewPage(sg)
        self.stack.addWidget(self.project_page)
        self.stack.addWidget(self.software_page)
        self.stack.addWidget(self.review_page)

        self.console = ConsolePanel()
        self.console.closed.connect(lambda: self.term_btn.setChecked(False))
        self.console.hide()

        self.split = QSplitter(Qt.Vertical)
        self.split.addWidget(self.stack)
        self.split.addWidget(self.console)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.split.setCollapsible(0, False)
        self.split.setHandleWidth(1)
        root.addWidget(self.split)

        QShortcut(QKeySequence("Ctrl+`"), self,
                  activated=self.term_btn.toggle)
        QShortcut(QKeySequence("Ctrl+K"), self,
                  activated=self.task_search.focus)

        self.project_page.project_selected.connect(self.open_project)
        self.software_page.software_launched.connect(self.launch_software)
        self.software_page.task_selected.connect(self._on_task_selected)
        self.software_page.package_launched.connect(self.launch_package)
        self.software_page.folder_requested.connect(self.open_folder)
        self.software_page.status_change_requested.connect(self.set_task_status)
        self.software_page.publish_requested.connect(self.publish_version)
        self.software_page.versions_requested.connect(self.view_versions)
        self.software_page.latest_version_requested.connect(
            self.open_latest_version)
        self.review_page.item_opened.connect(self.open_review_item)
        self.review_page.compare_requested.connect(self.compare_review_item)
        self.review_page.count_changed.connect(self._on_review_count)

        self.statusBar().showMessage("Connecting to ShotGrid...")
        self._run(self._bootstrap, self._on_bootstrap)

    # -- signed-in user ----------------------------------------------------

    AUTH_METHOD_LABELS = {
        "sso": "Workstation login (Active Directory)",
        "bind": "Password sign-in (Active Directory)",
        "dev": "Developer override (SGDESK_DEV_USER)",
        "disabled": "Authentication disabled in auth_config.yml",
    }

    def _build_user_chip(self):
        self.user_chip = UserChip(self.display_name, avatar_text=self.email)
        self.user_chip.setToolTip("Who Flow is signed in as")
        self.user_chip.clicked.connect(self._show_user_menu)
        # Kept for the tests and for anything that reads the header text.
        self.user_lbl = self.user_chip.name_lbl
        return self.user_chip

    def _user_details(self):
        """(label, value) rows for the profile menu, in reading order."""
        rows = [("Name", self.display_name),
                ("Login", self.login),
                ("Email", self.email)]
        if self.auth is not None:
            rows.append(("Signed in with",
                         self.AUTH_METHOD_LABELS.get(self.auth.method,
                                                     self.auth.method)))
            if getattr(self.auth, "domain", ""):
                rows.append(("Domain", self.auth.domain))
        if self.owner:
            rows.append(("ShotGrid",
                         self.owner.get("name") or self.owner.get("login", "")))
        else:
            rows.append(("ShotGrid", f"no {config.TASK_OWNER_ENTITY} matched "
                                     f"{self.email}"))
        return rows

    def _show_user_menu(self):
        menu = QMenu(self)
        for label, value in self._user_details():
            action = menu.addAction(f"{label}:  {value}")
            action.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Copy email address",
                       lambda: QApplication.clipboard().setText(self.email))
        menu.addAction("Copy login", lambda: QApplication.clipboard()
                       .setText(self.login))
        menu.exec(self.user_chip.mapToGlobal(
            self.user_chip.rect().bottomLeft()))

    # -- review inbox ------------------------------------------------------

    def show_review(self, shown):
        if shown:
            self._previous_page = self.stack.currentWidget()
            self.stack.setCurrentWidget(self.review_page)
            self.review_page.refresh()
        elif getattr(self, "_previous_page", None) is not None:
            self.stack.setCurrentWidget(self._previous_page)

    def _on_review_count(self, unread):
        self.review_btn.setText(
            f"Needs Attention ({unread})" if unread else "Needs Attention")
        # The same review data drives the dot on the task rows, so the two can
        # never disagree.
        self.software_page.set_attention(self.review_page.attention_by_task())

    def open_review_item(self, item):
        """Straight to the version the item is about, not to a search box."""
        version_id = (item.version or {}).get("id")
        if not version_id:
            QMessageBox.information(
                self, "Needs Attention",
                "This item is not linked to a version.")
            return
        task = item.task or self.task
        project = item.project or self.project
        if not task or not task.get("id"):
            self._open_version_in_browser(project, item)
            return
        self.review_btn.setChecked(False)
        browser = VersionBrowser(self.sg, project, self._full_task(task), self)
        browser.select_version(version_id)
        browser.exec()

    def _open_version_in_browser(self, project, item):
        QMessageBox.information(
            self, "Needs Attention",
            f"{item.headline()} on {item.version.get('code') or 'a version'}"
            f"\n\nThis note is not linked to a task, so Flow cannot open "
            f"the task's version list for it.")

    def _full_task(self, task):
        """The Task dict the browser needs, from the tasks already loaded."""
        for loaded in self.software_page.tasks._tasks:
            if loaded["id"] == task.get("id"):
                return loaded
        return dict(task, id=task["id"],
                    content=task.get("name") or task.get("content", ""))

    def compare_review_item(self, item):
        version_id = (item.version or {}).get("id")
        if not version_id:
            return
        self._run(lambda: self.sg.compare_pair(version_id),
                  lambda pair: self._show_compare(*pair),
                  on_error=lambda m: QMessageBox.warning(
                      self, "Compare", m))

    def _show_compare(self, newer, older):
        if not older:
            QMessageBox.information(
                self, "Compare",
                f"{newer.get('code') or 'This version'} is the first version "
                f"on its task — there is nothing before it to compare with.")
            return
        # Both playable: RV's own wipe, at full resolution and in the project's
        # colour space. The dialog is the fallback for media RV cannot reach.
        if rv_player.playable(newer) and rv_player.playable(older):
            try:
                rv_player.open_versions([newer, older], mode="wipe",
                                        project=self.project)
                return
            except Exception as e:
                log.error("could not open RV: %s", e)
        VersionCompare(self.sg, self.project, newer, older, parent=self).exec()

    def open_latest_version(self, task, version):
        """Open the task's newest version, selected in the browser."""
        self.task = task
        self.software_page.set_task(task)
        browser = VersionBrowser(self.sg, self.project, task, self)
        browser.select_version(version["id"])
        browser.exec()

    # -- terminal ----------------------------------------------------------

    def toggle_console(self, shown):
        self.console.setVisible(shown)
        # Hiding alone is not enough: the splitter keeps the pane's share and
        # leaves a dead strip at the bottom, so the sizes are set by hand.
        total = sum(self.split.sizes()) or self.split.height() or self.height()
        if shown:
            self.split.setSizes([int(total * 0.62), int(total * 0.38)])
        else:
            self.split.setSizes([total, 0])

    def show_console(self):
        if not self.term_btn.isChecked():
            self.term_btn.setChecked(True)

    # -- async helper ------------------------------------------------------

    def _run(self, fn, on_result, *args, on_error=None):
        """Run fn on the thread pool and hand the result back on the UI thread."""
        return jobs.run(
            self._jobs, fn, on_result, *args, pool=self.pool,
            on_error=on_error or
            (lambda msg: QMessageBox.critical(self, "ShotGrid", msg)))

    # -- data --------------------------------------------------------------

    def _bootstrap(self):
        owner = self.sg.resolve_owner(self.email)
        projects = self.sg.active_projects()
        statuses = self.sg.task_statuses()
        return owner, projects, statuses

    def _on_bootstrap(self, result):
        owner, projects, statuses = result
        self.owner = owner
        self._projects = projects
        self.software_page.set_statuses(statuses)
        if owner and owner.get("name"):
            self.user_chip.set_name(owner["name"])
        if not owner and config.TASK_OWNER_IS_ENTITY:
            self.statusBar().showMessage(
                f"No {config.TASK_OWNER_ENTITY} found with "
                f"{config.TASK_OWNER_MATCH_FIELD} '{self.email}' "
                f"— My Tasks will be empty")
        elif not owner:
            # String mode still works without the entity: it falls back to the
            # email address, which is probably what the tasks store anyway.
            self.statusBar().showMessage(
                f"Connected — {len(projects)} projects "
                f"(no {config.TASK_OWNER_ENTITY} for '{self.email}'; "
                f"matching tasks on the address itself)")
        else:
            self.statusBar().showMessage(f"Connected — {len(projects)} projects")
        self.project_page.set_projects(projects)

    # -- searching every project's tasks -------------------------------------

    def _load_all_tasks(self):
        """One query for the artist's whole workload, for the header search."""
        self._run(self.sg.all_my_tasks, self.task_search.set_tasks,
                  on_error=lambda m: log.warning(
                      "could not load the task search list: %s", m))

    def goto_task(self, task):
        """Open the task's project and land on the task itself."""
        project = self._project_for(task)
        if not project:
            QMessageBox.information(
                self, "Search",
                f"'{task.get('content', 'That task')}' is not on a project "
                f"Flow can open.")
            return
        if not self.project or self.project["id"] != project["id"]:
            self._pending_task_id = task["id"]
            self.open_project(project)
            return
        self._select_task(task["id"])

    def _project_for(self, task):
        """The full Project dict — the task's own carries only id and name."""
        link = task.get("project") or {}
        for project in self._projects:
            if project["id"] == link.get("id"):
                return project
        return link if link.get("id") else None

    def _select_task(self, task_id):
        if self.software_page.select_task(task_id):
            return True
        log.info("task %s is not in this project's task list", task_id)
        return False

    # -- navigation ---------------------------------------------------------

    def show_projects(self):
        self.project = None
        self.back_btn.hide()
        self.crumb.hide()
        self.crumb_project.hide()
        self.stack.setCurrentWidget(self.project_page)

    def open_project(self, project):
        self.project = project
        self.task = None
        self.software_page.set_task(None)
        self.software_page.set_project(project)
        self.crumb_project.setText(project["name"])
        self.crumb.show()
        self.crumb_project.show()
        self.back_btn.show()
        self.stack.setCurrentWidget(self.software_page)
        self.software_page.set_software([])
        self.software_page.set_loading()
        self.statusBar().showMessage("Loading apps and tasks...")

        self._run(self.sg.software_for_project, self._on_software, project)
        self._run(self.sg.my_tasks, self._on_tasks, project)

    def _on_software(self, softwares):
        self.software_page.set_software(softwares)
        self.statusBar().showMessage(f"{len(softwares)} apps available")

    def _on_tasks(self, tasks):
        self.software_page.set_tasks(tasks)
        if self._pending_task_id is not None:
            # Arrived here from the header search: the tasks only exist now.
            self._select_task(self._pending_task_id)
            self._pending_task_id = None
        if not tasks:
            return
        # One query for the whole page. A query per task is the N+1 that makes
        # a task list crawl on a show with real history.
        task_ids = [t["id"] for t in tasks]
        self._run(self.sg.latest_versions_for_tasks,
                  self.software_page.set_latest_versions, task_ids,
                  on_error=lambda m: log.warning(
                      "could not read latest versions: %s", m))
        # The review pass fills the dots on the same rows; it is separate
        # because it is worth having even when it fails.
        self.review_page.set_project(self.project)
        self.review_page.refresh()

    # -- launch --------------------------------------------------------------

    def _on_task_selected(self, task):
        self.task = task

    def launch_package(self, task, package, version):
        """Right-click launch: a DCC from the rez tree, opened on this task."""
        self.task = task
        self.software_page.set_task(task)
        try:
            pid, log_path = launcher.launch_package(
                self.project, package, version, task, self.login, self.email)
        except Exception as e:
            self._launch_failed(f"{package}-{version}", e)
            return
        self.console.tail(log_path)
        self.statusBar().showMessage(
            f"Launched {package}-{version} (pid {pid}) "
            f"on task '{task.get('content', '')}' — see Terminal for output")

    def launch_software(self, software):
        try:
            pid, log_path = launcher.launch(
                self.project, software, self.login, self.email, self.task)
        except Exception as e:
            self._launch_failed(software.get("code", "app"), e)
            return
        self.console.tail(log_path)
        where = (f"on task '{self.task['content']}'" if self.task
                 else "with no task context")
        self.statusBar().showMessage(
            f"Launched {software['code']} (pid {pid}) "
            f"in {self.project['name']} {where} — see Terminal for output")

    def publish_version(self, task):
        """Standalone publish: upload media as a Version against this task."""
        self.task = task
        self.software_page.set_task(task)
        log.info("standalone publish for task %s (%s)",
                 task["id"], task.get("content", ""))

        dialog = PublishDialog(self.sg, self.project, task, self.email, self)
        dialog.exec()
        result = dialog.published
        if result:
            self.statusBar().showMessage(
                f"Published Version {result.code} to "
                f"'{task.get('content', '')}' as {self.sg.api_identity}")

    def view_versions(self, task):
        """Browse what has already been published on this task's entity."""
        self.task = task
        self.software_page.set_task(task)
        if not task.get("entity"):
            QMessageBox.information(
                self, "Versions",
                "This task is not linked to a shot or asset, so it has no "
                "versions to browse.")
            return
        log.info("version browser for %s %s (task %s)",
                 task["entity"].get("type"), task["entity"].get("name"),
                 task["id"])
        VersionBrowser(self.sg, self.project, task, self).exec()

    def set_task_status(self, task, code):
        """Write a status change back to ShotGrid, off the UI thread."""
        task_id = task["id"]
        old = task.get("sg_status_list") or ""
        self.statusBar().showMessage(
            f"Setting '{task.get('content', '')}' to {code}…")
        # Show it straight away; put it back if the write fails.
        self.software_page.update_task_status(task_id, code)

        def write():
            self.sg.set_task_status(task_id, code)
            return task_id, code

        def done(result):
            _, new_code = result
            self.statusBar().showMessage(
                f"'{task.get('content', '')}' is now {new_code}")

        def failed(msg):
            log.error("could not set status on task %s: %s", task_id, msg)
            self.software_page.update_task_status(task_id, old)
            self.show_console()
            QMessageBox.warning(
                self, "Status not changed",
                f"ShotGrid rejected the change:\n\n{msg}\n\n"
                f"The task is still {old or 'unset'}.")

        self._run(write, done, on_error=failed)

    def open_folder(self, path):
        try:
            paths.open_folder(path)
            self.statusBar().showMessage(f"Opened {path}")
        except Exception as e:
            log.error("could not open %s: %s", path, e)
            QMessageBox.warning(self, "Open folder", str(e))

    def _launch_failed(self, what, error):
        """Open the Terminal on failure: the log says more than the dialog."""
        log.error("launch of %s failed: %s", what, error)
        self.show_console()
        QMessageBox.critical(
            self, "Launch failed",
            f"{error}\n\nThe Terminal panel shows the command that was tried.")
