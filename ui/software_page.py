from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QLabel, QMenu,
    QApplication, QStackedWidget, QAbstractItemView,
)

import config
import paths
import rez_scan
from . import theme
from .widgets import Tile, EmptyState, StatusPill, DueDate

TILE_WIDTH = 208


class SoftwareGrid(QWidget):
    software_launched = Signal(dict)

    def __init__(self):
        super().__init__()
        self._softwares = []
        self._cols = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(16)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        self.stack.addWidget(self.scroll)

        self.empty = EmptyState(
            "▤", "No apps configured for this project",
            "Apps here come from ShotGrid Software entities. You can also "
            "right-click a task in My Tasks to launch a DCC straight from "
            "the rez package tree.")
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.empty)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._relayout)

    def set_software(self, softwares):
        self._softwares = softwares
        self._cols = 0
        self._relayout()

    def _relayout(self):
        if not self._softwares:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(self.scroll)

        cols = max(1, self.scroll.viewport().width() // TILE_WIDTH)
        if cols == self._cols:
            return
        self._cols = cols

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row = col = 0
        for sw in self._softwares:
            tile = Tile(sw["code"], sw.get("image"),
                        subtitle=sw.get("version") or None)
            tile.clicked.connect(lambda s=sw: self.software_launched.emit(s))
            self.grid.addWidget(tile, row, col)
            col += 1
            if col >= cols:
                col, row = 0, row + 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()


class TasksTable(QWidget):
    COLS = ["Task", "Link", "Step", "Status", "Due"]

    task_selected = Signal(object)          # the Task dict, or None
    package_launched = Signal(object, str, str)   # task, package, version
    folder_requested = Signal(str)                # absolute path to open
    status_change_requested = Signal(object, str)   # task, new status code
    publish_requested = Signal(object)              # task
    versions_requested = Signal(object)             # task

    def __init__(self):
        super().__init__()
        self._tasks = []
        self._rows = []              # row index -> task dict, after filtering
        self._packages = []          # [(package, [versions]), ...] from disk
        self._project = None         # needed to build folder paths
        self._statuses = []          # [(code, label), ...] from the SG schema

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(12)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter tasks")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self._rebuild)
        top.addWidget(self.search)

        self.hint = QLabel("Right-click a task to open its folder or launch an app")
        self.hint.setObjectName("tileSub")
        top.addWidget(self.hint)
        top.addStretch()

        self.count = QLabel("")
        self.count.setObjectName("tileSub")
        top.addWidget(self.count)
        lay.addLayout(top)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)          # Task
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Link
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Step
        header.setSectionResizeMode(3, QHeaderView.Fixed)            # Status
        header.setSectionResizeMode(4, QHeaderView.Fixed)            # Due
        header.resizeSection(3, 110)
        header.resizeSection(4, 110)
        header.setHighlightSections(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setMouseTracking(True)      # so ::item:hover works
        self.table.setFocusPolicy(Qt.NoFocus)  # no dotted focus rectangle
        self.table.setItemDelegateForColumn(3, StatusPill(self.table))
        self.table.setItemDelegateForColumn(4, DueDate(self.table))
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.stack.addWidget(self.table)

        self.empty = EmptyState(
            "✓", "No tasks assigned to you on this project",
            "Tasks are matched on the sg_assigned_to field. If you expect "
            "tasks here, check the Terminal panel and README for how the "
            "match is configured.")
        self.stack.addWidget(self.empty)

    def set_tasks(self, tasks):
        self._tasks = tasks
        self._rebuild()

    def _on_selection(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.task_selected.emit(None)
            return
        r = rows[0].row()
        self.task_selected.emit(self._rows[r] if r < len(self._rows) else None)

    def set_project(self, project):
        self._project = project

    def _on_context_menu(self, pos):
        """Right-click a task: open its folder, or launch a DCC on it."""
        index = self.table.indexAt(pos)
        if not index.isValid() or index.row() >= len(self._rows):
            return
        task = self._rows[index.row()]
        self.table.selectRow(index.row())

        # Scanned lazily so a newly released package shows up without a
        # restart, and so a slow or absent mount costs nothing until asked.
        self._packages = rez_scan.scan()

        menu = QMenu(self)
        entity = (task.get("entity") or {}).get("name", "")
        header = menu.addAction(
            "Open {0} with…".format(entity or task.get("content", "task")))
        header.setEnabled(False)
        menu.addSeparator()

        self._add_publish_actions(menu, task)
        self._add_version_actions(menu, task)
        menu.addSeparator()

        self._add_status_actions(menu, task)
        menu.addSeparator()
        self._add_folder_actions(menu, task)
        menu.addSeparator()

        if not self._packages:
            empty = menu.addAction(
                "No packages found in {0}".format(config.DCC_PACKAGES_ROOT))
            empty.setEnabled(False)
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return

        for package, versions in self._packages:
            label = config.DCC_LABELS.get(package, package.title())
            if len(versions) == 1:
                act = QAction("{0}  {1}".format(label, versions[0]), menu)
                act.triggered.connect(
                    lambda _=False, p=package, v=versions[0]:
                    self.package_launched.emit(task, p, v))
                menu.addAction(act)
                continue
            sub = QMenu(label, menu)
            menu.addMenu(sub)
            for i, version in enumerate(versions):
                text = version + ("   (latest)" if i == 0 else "")
                act = QAction(text, sub)
                act.triggered.connect(
                    lambda _=False, p=package, v=version:
                    self.package_launched.emit(task, p, v))
                sub.addAction(act)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _add_publish_actions(self, menu, task):
        sub = QMenu("Publish", menu)
        menu.addMenu(sub)
        act = QAction("Standalone Publish…", sub)
        act.setToolTip("Upload a movie or image to ShotGrid as a Version, "
                       "without opening a DCC")
        act.triggered.connect(
            lambda _=False, t=task: self.publish_requested.emit(t))
        sub.addAction(act)
        return sub

    def _add_version_actions(self, menu, task):
        """Versions submenu, built with an explicit parent like the others."""
        sub = QMenu("Versions", menu)
        menu.addMenu(sub)
        act = QAction("View Versions…", sub)
        act.setToolTip("Browse the versions already published on this shot "
                       "or asset")
        act.triggered.connect(
            lambda _=False, t=task: self.versions_requested.emit(t))
        act.setEnabled(bool(task.get("entity")))
        sub.addAction(act)
        return sub

    def _add_status_actions(self, menu, task):
        """Set status submenu, with the task's current status ticked."""
        # Built with an explicit parent rather than menu.addMenu("..."), whose
        # return value PySide can collect out from under us.
        sub = QMenu("Set status", menu)
        menu.addMenu(sub)
        if not self._statuses:
            act = sub.addAction("Status list unavailable")
            act.setEnabled(False)
            return

        current = (task.get("sg_status_list") or "").lower()
        for code, label in self._statuses:
            act = QAction(f"{label}  ({code})", sub)
            act.setCheckable(True)
            act.setChecked(code.lower() == current)
            act.setEnabled(code.lower() != current)
            act.triggered.connect(
                lambda _=False, t=task, c=code:
                self.status_change_requested.emit(t, c))
            sub.addAction(act)

    def set_statuses(self, statuses):
        self._statuses = statuses or []

    def update_task(self, task_id, code):
        """Reflect a status write without refetching the whole task list."""
        for t in self._tasks:
            if t["id"] == task_id:
                t["sg_status_list"] = code
                break
        self._rebuild()

    def _add_folder_actions(self, menu, task):
        entries = paths.folders(self._project, task) if self._project else []
        if not entries:
            act = menu.addAction("No folder path for this task")
            act.setEnabled(False)
            act.setToolTip(
                "Needs a linked Shot with a sequence, or an Asset with a type")
            return

        root_label, root_path, root_exists = entries[0]
        root_act = QAction(root_label, menu)
        root_act.setToolTip(root_path)
        root_act.setEnabled(root_exists)
        root_act.triggered.connect(
            lambda _=False, p=root_path: self.folder_requested.emit(p))
        menu.addAction(root_act)

        sub = QMenu("Open folder", menu)
        menu.addMenu(sub)
        for label, path, exists in entries[1:]:
            act = QAction(label, sub)
            act.setToolTip(path)
            act.setEnabled(exists)      # greyed out means it was never created
            act.triggered.connect(
                lambda _=False, p=path: self.folder_requested.emit(p))
            sub.addAction(act)
        sub.addSeparator()
        copy = QAction("Copy path", sub)
        copy.triggered.connect(
            lambda _=False, p=root_path: QApplication.clipboard().setText(p))
        sub.addAction(copy)

    def _rebuild(self):
        text = self.search.text().lower()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self._rows = []

        for t in self._tasks:
            entity = (t.get("entity") or {}).get("name", "")
            step = (t.get("step") or {}).get("name", "")
            row_vals = [
                t.get("content", ""), entity, step,
                t.get("sg_status_list", ""), t.get("due_date") or "",
            ]
            if text and not any(text in str(v).lower() for v in row_vals):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            self._rows.append(t)
            for c, v in enumerate(row_vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if c == 1:                      # the shot or asset name
                    item.setForeground(QColor(theme.TEXT))
                elif c == 2:
                    item.setForeground(QColor(theme.TEXT_DIM))
                self.table.setItem(r, c, item)

        self.table.setUpdatesEnabled(True)

        total = len(self._tasks)
        shown = len(self._rows)
        self.count.setText(
            f"{shown} of {total}" if text and total else
            (f"{total} task{'s' if total != 1 else ''}" if total else ""))
        self.hint.setVisible(bool(shown))
        self.stack.setCurrentWidget(self.table if shown else self.empty)


class SoftwarePage(QWidget):
    software_launched = Signal(dict)
    task_selected = Signal(object)
    package_launched = Signal(object, str, str)
    folder_requested = Signal(str)
    status_change_requested = Signal(object, str)
    publish_requested = Signal(object)
    versions_requested = Signal(object)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.apps = SoftwareGrid()
        self.tasks = TasksTable()
        self.tabs.addTab(self.apps, "Apps")
        self.tabs.addTab(self.tasks, "My Tasks")
        lay.addWidget(self.tabs)

        # Which task an app will be launched against. Artists need to see this
        # before launching, because it decides where a publish lands.
        self.context_lbl = QLabel()
        self.context_lbl.setObjectName("contextBar")
        self.context_lbl.setContentsMargins(16, 6, 16, 6)
        lay.addWidget(self.context_lbl)
        self.set_task(None)

        self.apps.software_launched.connect(self.software_launched)
        self.tasks.task_selected.connect(self.set_task)
        self.tasks.task_selected.connect(self.task_selected)
        self.tasks.package_launched.connect(self.package_launched)
        self.tasks.folder_requested.connect(self.folder_requested)
        self.tasks.status_change_requested.connect(self.status_change_requested)
        self.tasks.publish_requested.connect(self.publish_requested)
        self.tasks.versions_requested.connect(self.versions_requested)

    def set_project(self, project):
        self.tasks.set_project(project)

    def set_statuses(self, statuses):
        self.tasks.set_statuses(statuses)

    def update_task_status(self, task_id, code):
        self.tasks.update_task(task_id, code)

    def set_software(self, softwares):
        self.apps.set_software(softwares)

    def set_tasks(self, tasks):
        self.tasks.set_tasks(tasks)

    def set_task(self, task):
        if not task:
            self.context_lbl.setObjectName("contextBarEmpty")
            self.context_lbl.setText(
                "  ○   No task selected — apps launch without a publish context")
        else:
            entity = (task.get("entity") or {}).get("name", "")
            step = (task.get("step") or {}).get("name", "")
            bits = [b for b in (entity, step, task.get("content", "")) if b]
            self.context_lbl.setObjectName("contextBar")
            self.context_lbl.setText(
                "  ●   Publishing to   " + "   ›   ".join(bits))
        # objectName drives the colour, so the style has to be re-applied
        self.context_lbl.style().unpolish(self.context_lbl)
        self.context_lbl.style().polish(self.context_lbl)
