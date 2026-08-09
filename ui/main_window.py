import getpass

from PySide6.QtCore import Qt, QThreadPool, QRunnable, QObject, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QMessageBox, QSplitter, QDialog,
)

import applog, config, launcher, paths
from .widgets import STYLE, Avatar
from .console import ConsolePanel
from .project_page import ProjectPage
from .publish_dialog import PublishDialog
from .software_page import SoftwarePage

log = applog.get()


class _WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class _Worker(QRunnable):
    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = _WorkerSignals()

    def run(self):
        try:
            self.signals.result.emit(self.fn(*self.args))
        except Exception as e:
            self.signals.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self, sg):
        super().__init__()
        self.sg = sg
        self.login = getpass.getuser()
        self.email = config.current_user_email(self.login)
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

        self.term_btn = QPushButton("Terminal")
        self.term_btn.setObjectName("termBtn")
        self.term_btn.setCheckable(True)
        self.term_btn.setCursor(Qt.PointingHandCursor)
        self.term_btn.setToolTip(
            "Show what ShotDeck is running in the background (Ctrl+`)")
        self.term_btn.toggled.connect(self.toggle_console)
        h.addWidget(self.term_btn)

        chip = QWidget()
        chip.setObjectName("userChip")
        chip_lay = QHBoxLayout(chip)
        chip_lay.setContentsMargins(4, 0, 10, 0)
        chip_lay.setSpacing(8)
        chip_lay.addWidget(Avatar(self.email))
        self.user_lbl = QLabel(self.email.split("@")[0])
        self.user_lbl.setToolTip(self.email)
        chip_lay.addWidget(self.user_lbl)
        h.addWidget(chip)
        root.addWidget(header)

        # pages, with the terminal as a collapsible bottom pane
        self.stack = QStackedWidget()
        self.project_page = ProjectPage()
        self.software_page = SoftwarePage()
        self.stack.addWidget(self.project_page)
        self.stack.addWidget(self.software_page)

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

        self.project_page.project_selected.connect(self.open_project)
        self.software_page.software_launched.connect(self.launch_software)
        self.software_page.task_selected.connect(self._on_task_selected)
        self.software_page.package_launched.connect(self.launch_package)
        self.software_page.folder_requested.connect(self.open_folder)
        self.software_page.status_change_requested.connect(self.set_task_status)
        self.software_page.publish_requested.connect(self.publish_version)

        self.statusBar().showMessage("Connecting to ShotGrid...")
        self._run(self._bootstrap, self._on_bootstrap)

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
        """Run fn on the thread pool and hand the result back on the UI thread.

        The worker is kept in _jobs until it finishes: QThreadPool takes the
        C++ object, but nothing holds the Python side, and a collected wrapper
        takes its signals with it — the callbacks then never fire.
        """
        worker = _Worker(fn, *args)
        self._jobs.add(worker)

        def finished(*_):
            self._jobs.discard(worker)

        worker.signals.result.connect(on_result)
        worker.signals.result.connect(finished)
        worker.signals.error.connect(
            on_error or
            (lambda msg: QMessageBox.critical(self, "ShotGrid", msg)))
        worker.signals.error.connect(finished)
        self.pool.start(worker)

    # -- data --------------------------------------------------------------

    def _bootstrap(self):
        owner = self.sg.resolve_owner(self.email)
        projects = self.sg.active_projects()
        statuses = self.sg.task_statuses()
        return owner, projects, statuses

    def _on_bootstrap(self, result):
        owner, projects, statuses = result
        self.software_page.set_statuses(statuses)
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
        self.software_page.set_tasks([])
        self.statusBar().showMessage("Loading apps and tasks...")

        self._run(self.sg.software_for_project, self._on_software, project)
        self._run(self.sg.my_tasks, self._on_tasks, project)

    def _on_software(self, softwares):
        self.software_page.set_software(softwares)
        self.statusBar().showMessage(f"{len(softwares)} apps available")

    def _on_tasks(self, tasks):
        self.software_page.set_tasks(tasks)

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
        if dialog.exec() == QDialog.Accepted:
            version = getattr(dialog, "published", None)
            if version:
                self.statusBar().showMessage(
                    f"Published Version {version.get('code') or version['id']} "
                    f"to '{task.get('content', '')}'")

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
