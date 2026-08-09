"""Publish a movie or image to ShotGrid as a Version, without opening a DCC."""

import os
import re

from PySide6.QtCore import Qt, QRunnable, QObject, Signal, QThreadPool, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QPlainTextEdit, QFileDialog, QProgressBar, QFrame,
    QSizePolicy, QWidget,
)

import applog
import config
from . import theme

log = applog.get()

PREVIEW_SIZE = (320, 180)

# Qt Multimedia is optional: it needs GStreamer plugins on Linux that a farm
# box may not have. Without it, movies simply show a file card instead.
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAVE_MULTIMEDIA = True
except ImportError:                                  # pragma: no cover
    HAVE_MULTIMEDIA = False


def is_movie(path):
    return os.path.splitext(path)[1].lower() in config.MOVIE_EXTENSIONS


def is_image(path):
    return os.path.splitext(path)[1].lower() in config.IMAGE_EXTENSIONS


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0


def suggest_name(task, existing):
    """Next version name for this task, following <entity>_<step>_v###."""
    entity = (task.get("entity") or {}).get("name") or "version"
    step = (task.get("step") or {}).get("name") or task.get("content") or ""
    stem = "_".join(p for p in (entity, step.replace(" ", "")) if p)

    highest = 0
    for v in existing or []:
        match = re.search(r"[._]v(\d+)\b", v.get("code") or "", re.IGNORECASE)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{stem}_v{highest + 1:03d}"


class _Signals(QObject):
    progress = Signal(str)
    done = Signal(object)
    failed = Signal(str)


class _PublishJob(QRunnable):
    def __init__(self, sg, project, task, name, path, description):
        super().__init__()
        self.args = (sg, project, task, name, path, description)
        self.signals = _Signals()

    def run(self):
        sg, project, task, name, path, description = self.args
        try:
            version = sg.publish_version(
                project, task, name, path, description,
                on_progress=self.signals.progress.emit)
            self.signals.done.emit(version)
        except Exception as e:
            log.error("publish failed: %s", e)
            self.signals.failed.emit(str(e))


class PublishDialog(QDialog):
    def __init__(self, sg, project, task, user_email, parent=None):
        super().__init__(parent)
        self.sg = sg
        self.project = project
        self.task = task
        self.path = ""
        self.player = None
        self._job = None            # kept alive while it runs

        self.setWindowTitle("Standalone Publish")
        self.setMinimumWidth(720)
        self.setStyleSheet(theme.STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        heading = QLabel("Publish a Version")
        heading.setObjectName("headerTitle")
        root.addWidget(heading)
        root.addWidget(self._context_card(user_email))

        # -- file picker
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Choose a movie or image to publish")
        self.file_edit.textChanged.connect(self._on_path_typed)
        file_row.addWidget(self.file_edit)

        browse = QPushButton("Browse…")
        browse.setObjectName("termBtn")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._browse)
        file_row.addWidget(browse)
        root.addLayout(file_row)

        # -- preview + fields side by side
        middle = QHBoxLayout()
        middle.setSpacing(16)

        self.preview_host = QFrame()
        self.preview_host.setObjectName("tile")
        self.preview_host.setFixedSize(*PREVIEW_SIZE)
        preview_lay = QVBoxLayout(self.preview_host)
        preview_lay.setContentsMargins(1, 1, 1, 1)
        self.preview = QLabel("No file selected")
        self.preview.setObjectName("emptyHint")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        preview_lay.addWidget(self.preview)
        middle.addWidget(self.preview_host, 0, Qt.AlignTop)

        fields = QVBoxLayout()
        fields.setSpacing(6)
        fields.addWidget(self._label("Version name"))
        self.name_edit = QLineEdit()
        fields.addWidget(self.name_edit)

        fields.addWidget(self._label("Description"))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("Optional — what changed in this version")
        self.desc_edit.setFixedHeight(84)
        fields.addWidget(self.desc_edit)

        self.file_info = QLabel("")
        self.file_info.setObjectName("tileSub")
        fields.addWidget(self.file_info)
        fields.addStretch()
        middle.addLayout(fields, 1)
        root.addLayout(middle)

        # -- progress + buttons
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)        # indeterminate; the API gives no %
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        root.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setObjectName("tileSub")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("consoleBtn")
        self.cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_btn)

        self.publish_btn = QPushButton("Publish")
        self.publish_btn.setObjectName("termBtn")
        self.publish_btn.setCursor(Qt.PointingHandCursor)
        self.publish_btn.setEnabled(False)
        self.publish_btn.clicked.connect(self._publish)
        buttons.addWidget(self.publish_btn)
        root.addLayout(buttons)

        self._suggest_name()

    # -- construction helpers ---------------------------------------------

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("tileSub")
        return lbl

    def _context_card(self, user_email):
        """What this will be published against, so nobody has to guess."""
        card = QFrame()
        card.setObjectName("tile")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)

        entity = self.task.get("entity") or {}
        step = (self.task.get("step") or {}).get("name", "")
        rows = [
            ("Project", self.project["name"]),
            (entity.get("type") or "Entity", entity.get("name") or "—"),
            ("Task", f"{self.task.get('content', '')}"
                     f"{'  ·  ' + step if step else ''}"),
            ("User", user_email),
        ]
        for r, (key, value) in enumerate(rows):
            k = QLabel(key)
            k.setObjectName("tileSub")
            v = QLabel(str(value))
            v.setObjectName("tileName")
            grid.addWidget(k, r, 0, Qt.AlignRight)
            grid.addWidget(v, r, 1)
        grid.setColumnStretch(1, 1)
        return card

    def _suggest_name(self):
        """Ask ShotGrid what versions already exist so v### continues."""
        try:
            existing = self.sg.versions_for_task(self.task["id"])
        except Exception as e:
            log.warning("could not list existing versions: %s", e)
            existing = []
        self.name_edit.setText(suggest_name(self.task, existing))

    # -- file selection ----------------------------------------------------

    def _browse(self):
        movies = " ".join(f"*{e}" for e in sorted(config.MOVIE_EXTENSIONS))
        images = " ".join(f"*{e}" for e in sorted(config.IMAGE_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select media to publish", os.path.expanduser("~"),
            f"Media ({movies} {images});;Movies ({movies});;"
            f"Images ({images});;All files (*)")
        if path:
            self.file_edit.setText(path)

    def _on_path_typed(self, text):
        self.path = text.strip()
        valid = bool(self.path) and os.path.isfile(self.path)
        self.publish_btn.setEnabled(valid)

        if not self.path:
            self.file_info.setText("")
            self._show_message("No file selected")
            return
        if not valid:
            self.file_info.setText("")
            self._show_message("File not found")
            return

        size = human_size(os.path.getsize(self.path))
        kind = "Movie" if is_movie(self.path) else \
               ("Image" if is_image(self.path) else "File")
        self.file_info.setText(
            f"{kind}  ·  {size}\n{os.path.basename(self.path)}")
        self.file_info.setToolTip(self.path)
        self._load_preview()

    # -- preview -----------------------------------------------------------

    def _clear_preview(self):
        if self.player is not None:
            self.player.stop()
            self.player = None
        layout = self.preview_host.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_message(self, text):
        self._clear_preview()
        self.preview = QLabel(text)
        self.preview.setObjectName("emptyHint")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview_host.layout().addWidget(self.preview)

    def _load_preview(self):
        if is_image(self.path):
            pm = QPixmap(self.path)
            if pm.isNull():
                # Qt has no reader for EXR or DPX without a plugin.
                self._show_message(
                    f"No preview for {os.path.splitext(self.path)[1]} files.\n"
                    f"It will still be published.")
                return
            self._clear_preview()
            self.preview = QLabel()
            self.preview.setAlignment(Qt.AlignCenter)
            self.preview.setPixmap(pm.scaled(
                PREVIEW_SIZE[0] - 2, PREVIEW_SIZE[1] - 2,
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.preview_host.layout().addWidget(self.preview)
            return

        if is_movie(self.path) and HAVE_MULTIMEDIA:
            self._play_movie()
            return

        self._show_message(
            "No preview available for this file.\nIt will still be published."
            if not is_movie(self.path) else
            "Video preview needs Qt Multimedia,\nwhich is not available here.")

    def _play_movie(self):
        self._clear_preview()
        video = QVideoWidget()
        video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_host.layout().addWidget(video)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setMuted(True)          # nobody wants a surprise soundtrack
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(video)
        self.player.errorOccurred.connect(
            lambda *_: self._show_message(
                "Could not decode this video for preview.\n"
                "It will still be published."))
        self.player.setSource(QUrl.fromLocalFile(self.path))
        self.player.play()

    # -- publishing --------------------------------------------------------

    def _publish(self):
        name = self.name_edit.text().strip()
        if not name:
            self.status.setText("Give the version a name first.")
            return
        if not os.path.isfile(self.path):
            self.status.setText("That file no longer exists.")
            return

        self._set_busy(True)
        job = _PublishJob(self.sg, self.project, self.task, name, self.path,
                          self.desc_edit.toPlainText().strip())
        job.signals.progress.connect(self.status.setText)
        job.signals.done.connect(self._on_done)
        job.signals.failed.connect(self._on_failed)
        self._job = job                    # keep the wrapper alive
        QThreadPool.globalInstance().start(job)

    def _set_busy(self, busy):
        self.progress.setVisible(busy)
        self.publish_btn.setEnabled(not busy)
        self.file_edit.setEnabled(not busy)
        self.name_edit.setEnabled(not busy)
        self.desc_edit.setEnabled(not busy)
        self.cancel_btn.setText("Close" if busy else "Cancel")

    def _on_done(self, version):
        self._set_busy(False)
        self.progress.hide()
        self.published = version
        self.status.setText(
            f"Published — Version {version['id']} created and media uploaded.")
        log.info("published Version %s for task %s",
                 version["id"], self.task["id"])
        self.accept()

    def _on_failed(self, message):
        self._set_busy(False)
        self.progress.hide()
        self.status.setText(f"Failed: {message}")

    def closeEvent(self, event):
        if self.player is not None:
            self.player.stop()
        super().closeEvent(event)
