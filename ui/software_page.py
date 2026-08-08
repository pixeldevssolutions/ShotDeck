from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QLabel, QMenu,
)

import config
import rez_scan
from .widgets import Tile


class SoftwareGrid(QWidget):
    software_launched = Signal(dict)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        lay.addWidget(self.scroll)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

    def set_software(self, softwares):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = max(1, self.width() // 175)
        row = col = 0
        for sw in softwares:
            sub = sw.get("version") or ""
            tile = Tile(sw["code"], sw.get("image"), subtitle=sub)
            tile.clicked.connect(lambda s=sw: self.software_launched.emit(s))
            self.grid.addWidget(tile, row, col)
            col += 1
            if col >= cols:
                col, row = 0, row + 1


class TasksTable(QWidget):
    COLS = ["Task", "Link", "Step", "Status", "Due"]

    task_selected = Signal(object)          # the Task dict, or None
    package_launched = Signal(object, str, str)   # task, package, version

    def __init__(self):
        super().__init__()
        self._tasks = []
        self._rows = []              # row index -> task dict, after filtering
        self._packages = []          # [(package, [versions]), ...] from disk
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter tasks...")
        self.search.textChanged.connect(self._rebuild)
        lay.addWidget(self.search)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self.table)

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

    def _on_context_menu(self, pos):
        """Right-click a task: pick a DCC and version to open it with."""
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
            sub = menu.addMenu(label)
            for i, version in enumerate(versions):
                text = version + ("   (latest)" if i == 0 else "")
                act = QAction(text, sub)
                act.triggered.connect(
                    lambda _=False, p=package, v=version:
                    self.package_launched.emit(task, p, v))
                sub.addAction(act)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _rebuild(self):
        text = self.search.text().lower()
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
                self.table.setItem(r, c, item)


class SoftwarePage(QWidget):
    software_launched = Signal(dict)
    task_selected = Signal(object)
    package_launched = Signal(object, str, str)

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

    def set_software(self, softwares):
        self.apps.set_software(softwares)

    def set_tasks(self, tasks):
        self.tasks.set_tasks(tasks)

    def set_task(self, task):
        if not task:
            self.context_lbl.setText(
                "No task selected — apps launch without a publish context. "
                "Pick one in My Tasks.")
            return
        entity = (task.get("entity") or {}).get("name", "")
        step = (task.get("step") or {}).get("name", "")
        bits = [b for b in (entity, step, task.get("content", "")) if b]
        self.context_lbl.setText("Publishing to:  " + "  ›  ".join(bits))
