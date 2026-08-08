"""The Terminal panel: what ShotDeck did, and what the launched app is saying.

Two sources feed it:

  * the session log, mirrored live through applog.subscribe()
  * the log file of the most recently launched process, tailed on a timer

Tailing a file rather than reading a pipe is deliberate -- see launcher.launch().
A poll is used instead of QFileSystemWatcher because the logs may sit on NFS,
where watches are unreliable.
"""

import logging
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QLabel,
    QCheckBox, QFileDialog,
)

import applog

POLL_MS = 400
MAX_BLOCKS = 5000        # trim scrollback; DCCs can be very chatty

LEVEL_COLOURS = {
    logging.DEBUG: "#7f7f7f",
    logging.INFO: "#d5d5d5",
    logging.WARNING: "#e0b040",
    logging.ERROR: "#e06c60",
    logging.CRITICAL: "#e06c60",
}


class ConsolePanel(QWidget):
    """Log view with a live tail of the current launch."""

    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("console")
        self._tail_path = None
        self._tail_pos = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("consoleBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 4, 6, 4)

        self.title = QLabel("Terminal")
        self.title.setObjectName("consoleTitle")
        h.addWidget(self.title)

        self.source = QLabel("")
        self.source.setObjectName("consoleSource")
        h.addWidget(self.source)
        h.addStretch()

        self.follow = QCheckBox("Follow")
        self.follow.setChecked(True)
        h.addWidget(self.follow)

        for text, slot in (("Copy", self._copy), ("Save…", self._save),
                           ("Clear", self._clear), ("✕", self._close)):
            btn = QPushButton(text)
            btn.setObjectName("consoleBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            h.addWidget(btn)

        lay.addWidget(bar)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(MAX_BLOCKS)
        self.view.setFont(QFont("DejaVu Sans Mono", 9))
        self.view.setObjectName("consoleView")
        lay.addWidget(self.view)

        applog.subscribe(self._on_log_record)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_tail)
        self._timer.start(POLL_MS)

    # -- log sources -------------------------------------------------------

    def _on_log_record(self, line, levelno):
        """Called from whichever thread logged; Qt text edits are main-thread
        only, so hop across with a queued single-shot."""
        QTimer.singleShot(0, lambda: self._append(line, levelno))

    def tail(self, path):
        """Start following a launched process's log file."""
        self._tail_path = path
        self._tail_pos = 0
        self.source.setText("— " + os.path.basename(path) if path else "")

    def _poll_tail(self):
        if not self._tail_path or not os.path.isfile(self._tail_path):
            return
        try:
            size = os.path.getsize(self._tail_path)
            if size < self._tail_pos:      # file was rotated or truncated
                self._tail_pos = 0
            if size == self._tail_pos:
                return
            with open(self._tail_path, "r", errors="replace") as f:
                f.seek(self._tail_pos)
                chunk = f.read()
                self._tail_pos = f.tell()
        except OSError:
            return
        for line in chunk.splitlines():
            self._append(line, logging.INFO, raw=True)

    # -- view --------------------------------------------------------------

    def _append(self, line, levelno=logging.INFO, raw=False):
        colour = LEVEL_COLOURS.get(levelno, "#d5d5d5")
        if raw and line.startswith("#"):
            colour = "#6f8f6f"          # launch-log header comments
        safe = (line.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))
        self.view.appendHtml(
            f'<span style="color:{colour}; white-space:pre">{safe}</span>')
        if self.follow.isChecked():
            self.view.moveCursor(QTextCursor.End)

    def _copy(self):
        self.view.selectAll()
        self.view.copy()
        cursor = self.view.textCursor()
        cursor.clearSelection()
        self.view.setTextCursor(cursor)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save log", os.path.expanduser("~/shotdeck-log.txt"))
        if path:
            with open(path, "w") as f:
                f.write(self.view.toPlainText())

    def _clear(self):
        self.view.clear()

    def _close(self):
        self.closed.emit()

    def closeEvent(self, event):     # pragma: no cover - Qt teardown
        applog.unsubscribe(self._on_log_record)
        super().closeEvent(event)
