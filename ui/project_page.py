from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea, QGridLayout,
    QLabel, QStackedWidget,
)

from .widgets import Tile, EmptyState

TILE_WIDTH = 208     # tile plus spacing, used to work out the column count


class ProjectPage(QWidget):
    project_selected = Signal(dict)

    def __init__(self):
        super().__init__()
        self._projects = []
        self._cols = 0           # last column count we laid out for

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(14)

        top = QHBoxLayout()
        heading = QLabel("Projects")
        heading.setObjectName("headerTitle")
        top.addWidget(heading)

        self.count = QLabel("")
        self.count.setObjectName("tileSub")
        top.addWidget(self.count)
        top.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search projects")
        self.search.setFixedWidth(240)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._rebuild)
        top.addWidget(self.search)
        lay.addLayout(top)

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
            "◵", "Loading projects…",
            "If this stays empty, check the Terminal panel for connection errors.")
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.empty)

        # Relayout once the drag settles rather than on every resize event.
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._relayout)

    def set_projects(self, projects):
        self._projects = projects
        if not projects:
            self.empty.deleteLater()
            self.empty = EmptyState(
                "○", "No active projects",
                "Nothing on this site has sg_status set to Active.")
            self.stack.addWidget(self.empty)
        self._rebuild()

    def _rebuild(self):
        self._cols = 0          # force the grid to be rebuilt
        self._relayout()

    def _relayout(self):
        text = self.search.text().lower()
        shown = [p for p in self._projects
                 if not text or text in p["name"].lower()]

        self.count.setText(
            f"{len(shown)} of {len(self._projects)}" if text
            else (f"{len(shown)}" if shown else ""))

        if not shown:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(self.scroll)

        cols = max(1, self.scroll.viewport().width() // TILE_WIDTH)
        if cols == self._cols:
            return              # nothing moved, keep the tiles we have
        self._cols = cols

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row = col = 0
        for proj in shown:
            tile = Tile(proj["name"], proj.get("image"),
                        subtitle=proj.get("tank_name") or None)
            tile.clicked.connect(lambda p=proj: self.project_selected.emit(p))
            self.grid.addWidget(tile, row, col)
            col += 1
            if col >= cols:
                col, row = 0, row + 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()
