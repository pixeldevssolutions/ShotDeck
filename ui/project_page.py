from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QScrollArea, QGridLayout,
)

from .widgets import Tile


class ProjectPage(QWidget):
    project_selected = Signal(dict)

    def __init__(self):
        super().__init__()
        self._projects = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search projects...")
        self.search.textChanged.connect(self._rebuild)
        lay.addWidget(self.search)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        lay.addWidget(self.scroll)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

    def set_projects(self, projects):
        self._projects = projects
        self._rebuild()

    def _rebuild(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        text = self.search.text().lower()
        cols = max(1, self.width() // 175)
        row = col = 0
        for proj in self._projects:
            if text and text not in proj["name"].lower():
                continue
            tile = Tile(proj["name"], proj.get("image"))
            tile.clicked.connect(lambda p=proj: self.project_selected.emit(p))
            self.grid.addWidget(tile, row, col)
            col += 1
            if col >= cols:
                col, row = 0, row + 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild()
