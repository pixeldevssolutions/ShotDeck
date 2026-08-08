import getpass

from PySide6.QtCore import Qt, QThreadPool, QRunnable, QObject, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QMessageBox,
)

import config, launcher
from .widgets import STYLE
from .project_page import ProjectPage
from .software_page import SoftwarePage


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

        self.setWindowTitle(config.APP_TITLE)
        self.resize(880, 640)
        self.setStyleSheet(STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(48)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 0, 16, 0)

        self.back_btn = QPushButton("\u2039 Projects")
        self.back_btn.setObjectName("backBtn")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.show_projects)
        self.back_btn.hide()
        h.addWidget(self.back_btn)

        self.title = QLabel(config.APP_TITLE)
        self.title.setObjectName("headerTitle")
        h.addWidget(self.title)
        h.addStretch()

        self.user_lbl = QLabel(self.email)
        h.addWidget(self.user_lbl)
        root.addWidget(header)

        # pages
        self.stack = QStackedWidget()
        self.project_page = ProjectPage()
        self.software_page = SoftwarePage()
        self.stack.addWidget(self.project_page)
        self.stack.addWidget(self.software_page)
        root.addWidget(self.stack)

        self.project_page.project_selected.connect(self.open_project)
        self.software_page.software_launched.connect(self.launch_software)
        self.software_page.task_selected.connect(self._on_task_selected)

        self.statusBar().showMessage("Connecting to ShotGrid...")
        self._run(self._bootstrap, self._on_bootstrap)

    # -- async helper ------------------------------------------------------

    def _run(self, fn, on_result, *args):
        worker = _Worker(fn, *args)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(
            lambda msg: QMessageBox.critical(self, "ShotGrid", msg))
        self.pool.start(worker)

    # -- data --------------------------------------------------------------

    def _bootstrap(self):
        owner = self.sg.resolve_owner(self.email)
        projects = self.sg.active_projects()
        return owner, projects

    def _on_bootstrap(self, result):
        owner, projects = result
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
        self.title.setText(config.APP_TITLE)
        self.stack.setCurrentWidget(self.project_page)

    def open_project(self, project):
        self.project = project
        self.task = None
        self.software_page.set_task(None)
        self.title.setText(project["name"])
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

    def launch_software(self, software):
        try:
            pid = launcher.launch(
                self.project, software, self.login, self.email, self.task)
            where = (f"on task '{self.task['content']}'" if self.task
                     else "with no task context")
            self.statusBar().showMessage(
                f"Launched {software['code']} (pid {pid}) "
                f"in {self.project['name']} {where}")
        except Exception as e:
            QMessageBox.critical(self, "Launch failed", str(e))
