from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
)

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

    def __init__(self):
        super().__init__()
        self._tasks = []
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
        lay.addWidget(self.table)

    def set_tasks(self, tasks):
        self._tasks = tasks
        self._rebuild()

    def _rebuild(self):
        text = self.search.text().lower()
        self.table.setRowCount(0)
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
            for c, v in enumerate(row_vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(r, c, item)


class SoftwarePage(QWidget):
    software_launched = Signal(dict)

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

        self.apps.software_launched.connect(self.software_launched)

    def set_software(self, softwares):
        self.apps.set_software(softwares)

    def set_tasks(self, tasks):
        self.tasks.set_tasks(tasks)
