from PySide6.QtCore import Qt, QSize, Signal, QThreadPool, QRunnable, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QSizePolicy,
)
import urllib.request

_pool = QThreadPool.globalInstance()


class _ThumbSignals(QObject):
    done = Signal(bytes)


class _ThumbJob(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = _ThumbSignals()

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                self.signals.done.emit(r.read())
        except Exception:
            pass


class Tile(QFrame):
    """SG Desktop style tile: thumbnail on top, label below."""
    clicked = Signal()

    def __init__(self, title, image_url=None, subtitle=None, size=QSize(140, 140)):
        super().__init__()
        self.setObjectName("tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(size.width() + 20, size.height() + 56)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(6)

        self.thumb = QLabel()
        self.thumb.setObjectName("tileThumb")
        self.thumb.setFixedSize(size)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setText(title[:2].upper())
        lay.addWidget(self.thumb, alignment=Qt.AlignHCenter)

        name = QLabel(title)
        name.setObjectName("tileName")
        name.setAlignment(Qt.AlignHCenter)
        lay.addWidget(name)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("tileSub")
            sub.setAlignment(Qt.AlignHCenter)
            lay.addWidget(sub)

        if image_url:
            job = _ThumbJob(image_url)
            job.signals.done.connect(self._set_thumb)
            _pool.start(job)

    def _set_thumb(self, data):
        pm = QPixmap()
        if pm.loadFromData(data):
            self.thumb.setPixmap(pm.scaled(
                self.thumb.size(), Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation))
            self.thumb.setText("")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


STYLE = """
QMainWindow, QWidget { background: #2b2b2b; color: #d5d5d5;
    font-family: 'Open Sans', 'Segoe UI', sans-serif; font-size: 12px; }
#header { background: #1f1f1f; }
#contextBar { background: #1f1f1f; color: #8f8f8f; border-top: 1px solid #3a3a3a; }
#headerTitle { font-size: 15px; font-weight: 600; color: #ffffff; }
#backBtn { background: transparent; border: none; color: #18a7e0;
    font-size: 13px; padding: 4px 10px; }
#backBtn:hover { color: #4fc3f7; }
#tile { background: #333333; border: 1px solid #3d3d3d; border-radius: 6px; }
#tile:hover { background: #3c3c3c; border-color: #18a7e0; }
#tileThumb { background: #222222; border-radius: 4px; color: #666;
    font-size: 28px; font-weight: 700; }
#tileName { color: #eaeaea; font-weight: 600; }
#tileSub { color: #8a8a8a; font-size: 11px; }
QLineEdit { background: #1f1f1f; border: 1px solid #3d3d3d; border-radius: 4px;
    padding: 6px 10px; color: #eaeaea; }
QLineEdit:focus { border-color: #18a7e0; }
QTableWidget { background: #2b2b2b; gridline-color: #3a3a3a;
    alternate-background-color: #303030; border: none; }
QHeaderView::section { background: #1f1f1f; color: #9a9a9a; border: none;
    padding: 6px; font-weight: 600; }
QTabBar::tab { background: transparent; color: #9a9a9a; padding: 8px 18px; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #18a7e0; }
QTabWidget::pane { border: none; }
QStatusBar { background: #1f1f1f; color: #8a8a8a; }
QScrollArea { border: none; }
"""
