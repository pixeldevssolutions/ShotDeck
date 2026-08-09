"""The Standalone Publish dialog.

Input, preview and progress only: every decision about what a publish means
lives in `publish_service`, so it can be tested without a screen. The dialog
knows how to show a stage, an error and a result, and nothing else.
"""

import os

from PySide6.QtCore import Qt, QRunnable, QObject, Signal, QThreadPool, QUrl, \
    QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QPlainTextEdit, QFileDialog, QProgressBar, QFrame,
    QSizePolicy, QStackedWidget, QMessageBox,
)

import applog
import config
import media_inspector
import paths
import publish_service
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

human_size = media_inspector.human_size


def is_movie(path):
    return config.media_kind(path) == "movie"


def is_image(path):
    return config.media_kind(path) == "image"


def is_media(path):
    return bool(config.media_kind(path))


def is_workfile(path):
    return os.path.splitext(path)[1].lower() in config.WORKFILE_EXTENSIONS


def suggest_name(task, existing):
    """Kept as a module function: older callers and tests import it here."""
    return publish_service.next_version_name(task, existing)


def dropped_files(mime):
    """Local file paths in a drag, in the order they were dragged."""
    if not mime.hasUrls():
        return []
    return [u.toLocalFile() for u in mime.urls()
            if u.isLocalFile() and os.path.isfile(u.toLocalFile())]


# -- background work --------------------------------------------------------

class _Signals(QObject):
    progress = Signal(str)
    done = Signal(object)
    failed = Signal(object)


class _PublishJob(QRunnable):
    """Runs one publish on the thread pool. Cancellable between stages."""

    def __init__(self, service, request):
        super().__init__()
        self.service = service
        self.request = request
        self.signals = _Signals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result = self.service.publish(
                self.request,
                on_stage=self.signals.progress.emit,
                cancelled=lambda: self._cancelled)
            self.signals.done.emit(result)
        except publish_service.PublishError as e:
            log.error("publish failed: %s (%s)", e, e.detail or "no detail")
            self.signals.failed.emit(e)
        except Exception as e:                       # pragma: no cover
            log.error("publish failed: %s", e)
            self.signals.failed.emit(publish_service.friendly(e))


class _InspectJob(QRunnable):
    """ffprobe off the UI thread -- a cold NFS read is not instant."""

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.done.emit(media_inspector.inspect(self.path))
        except Exception as e:                       # pragma: no cover
            self.signals.failed.emit(e)


class DropZone(QFrame):
    """The preview area, which doubles as the target for a dragged file.

    Dropping anywhere on the dialog works too (PublishDialog handles it); this
    is the part that says so, and lights up when a file is over it.
    """

    dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)

    def _highlight(self, on):
        self.setObjectName("dropZoneActive" if on else "dropZone")
        # A changed objectName only repaints after the style is re-applied.
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if dropped_files(event.mimeData()):
            event.acceptProposedAction()
            self._highlight(True)

    def dragLeaveEvent(self, event):
        self._highlight(False)

    def dropEvent(self, event):
        self._highlight(False)
        files = dropped_files(event.mimeData())
        if files:
            event.acceptProposedAction()
            self.dropped.emit(files[0])


class PublishDialog(QDialog):
    def __init__(self, sg, project, task, user_email, parent=None):
        super().__init__(parent)
        self.sg = sg
        self.service = publish_service.PublishService(sg)
        self.project = project
        self.task = task
        self.user_email = user_email

        self.path = ""
        self.work_path = ""
        self.media_info = None
        self.published = None
        self.player = None
        self._job = None            # kept alive while it runs
        self._inspect = None
        self._existing = []         # Versions already on this task

        self.setWindowTitle("Standalone Publish")
        self.setMinimumWidth(760)
        self.setStyleSheet(theme.STYLE)
        self.setAcceptDrops(True)   # dropping anywhere on the dialog works

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        self.pages = QStackedWidget()
        root.addWidget(self.pages)
        self.pages.addWidget(self._form_page())
        self.result_page = _ResultPage(self)
        self.pages.addWidget(self.result_page)

        # Typing a name checks it against the task's existing versions, but not
        # on every keystroke.
        self._name_timer = QTimer(self)
        self._name_timer.setSingleShot(True)
        self._name_timer.setInterval(config.SEARCH_DEBOUNCE_MS)
        self._name_timer.timeout.connect(self._check_name)

        self._load_existing()

    # -- construction ------------------------------------------------------

    def _form_page(self):
        page = QFrame()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        heading = QLabel("Publish a Version")
        heading.setObjectName("headerTitle")
        root.addWidget(heading)
        root.addWidget(self._context_card())

        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText(
            "Drop a movie or image here, or browse for one")
        # Let a drop fall through to the dialog instead of the line edit
        # pasting the file:// URL as text.
        self.file_edit.setAcceptDrops(False)
        self.file_edit.textChanged.connect(self._on_path_typed)
        file_row.addWidget(self.file_edit)

        browse = QPushButton("Choose Image / Movie…")
        browse.setObjectName("termBtn")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._browse)
        file_row.addWidget(browse)
        root.addLayout(file_row)

        work_row = QHBoxLayout()
        self.work_edit = QLineEdit()
        self.work_edit.setPlaceholderText(
            "Optional — the scene file this came from (.nk, .ma, .hip …)")
        self.work_edit.setAcceptDrops(False)
        self.work_edit.textChanged.connect(self._on_work_typed)
        work_row.addWidget(self.work_edit)

        work_browse = QPushButton("Browse…")
        work_browse.setObjectName("termBtn")
        work_browse.setCursor(Qt.PointingHandCursor)
        work_browse.clicked.connect(self._browse_work)
        work_row.addWidget(work_browse)

        self.work_clear = QPushButton("Clear")
        self.work_clear.setObjectName("consoleBtn")
        self.work_clear.setCursor(Qt.PointingHandCursor)
        self.work_clear.clicked.connect(self.work_edit.clear)
        self.work_clear.hide()
        work_row.addWidget(self.work_clear)
        root.addLayout(work_row)

        middle = QHBoxLayout()
        middle.setSpacing(16)

        self.preview_host = DropZone()
        self.preview_host.dropped.connect(self.accept_file)
        self.preview_host.setFixedSize(*PREVIEW_SIZE)
        preview_lay = QVBoxLayout(self.preview_host)
        preview_lay.setContentsMargins(1, 1, 1, 1)
        self.preview = QLabel("Drop a file here")
        self.preview.setObjectName("dropHint")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        preview_lay.addWidget(self.preview)
        middle.addWidget(self.preview_host, 0, Qt.AlignTop)

        fields = QVBoxLayout()
        fields.setSpacing(6)
        fields.addWidget(_sub("Version name"))
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(lambda _: self._name_timer.start())
        fields.addWidget(self.name_edit)

        self.name_warning = QLabel("")
        self.name_warning.setObjectName("warnText")
        self.name_warning.setWordWrap(True)
        self.name_warning.hide()
        fields.addWidget(self.name_warning)

        fields.addWidget(_sub("Description"))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("Optional — what changed in this version")
        self.desc_edit.setFixedHeight(72)
        fields.addWidget(self.desc_edit)

        self.file_info = QLabel("")
        self.file_info.setObjectName("tileSub")
        self.file_info.setWordWrap(True)
        fields.addWidget(self.file_info)

        self.work_info = QLabel("")
        self.work_info.setObjectName("tileSub")
        fields.addWidget(self.work_info)
        fields.addStretch()
        middle.addLayout(fields, 1)
        root.addLayout(middle)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)        # see _set_busy for why
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        root.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setObjectName("tileSub")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("consoleBtn")
        self.cancel_btn.clicked.connect(self._on_cancel)
        buttons.addWidget(self.cancel_btn)

        self.publish_btn = QPushButton("Publish Version")
        self.publish_btn.setObjectName("termBtn")
        self.publish_btn.setCursor(Qt.PointingHandCursor)
        self.publish_btn.setEnabled(False)
        self.publish_btn.clicked.connect(self._publish)
        buttons.addWidget(self.publish_btn)
        root.addLayout(buttons)
        return page

    def _context_card(self):
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
            ("Task", self.task.get("content", "")),
            ("Department", step or "—"),
            ("User", self.user_email),
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

    # -- existing versions and naming --------------------------------------

    def _load_existing(self):
        try:
            self._existing = self.sg.versions_for_task(self.task["id"]) or []
        except Exception as e:
            log.warning("could not list existing versions: %s", e)
            self._existing = []
        self.name_edit.setText(
            publish_service.next_version_name(self.task, self._existing))

    def _check_name(self):
        """Advisory duplicate check against what the task already has.

        The authoritative check runs server-side just before the create, in
        PublishService -- this one is here so the artist finds out while
        typing rather than after a 1.4 GB upload.
        """
        name = self.name_edit.text().strip()
        clash = any((v.get("code") or "").lower() == name.lower()
                    for v in self._existing)
        if clash:
            self.name_warning.setText(
                f"Version already exists:  {name}\nChoose another version "
                f"name — nothing is ever overwritten.")
            self.name_warning.show()
        else:
            self.name_warning.hide()
        self._refresh_publish_enabled()
        return not clash

    # -- file selection ----------------------------------------------------

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select media to publish", os.path.expanduser("~"),
            config.media_filter())
        if path:
            self.file_edit.setText(path)

    def _browse_work(self):
        exts = " ".join(f"*{e}" for e in sorted(config.WORKFILE_EXTENSIONS))
        start = os.path.dirname(self.path) if self.path \
            else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select the scene file this came from", start,
            f"Scene files ({exts});;All files (*)")
        if path:
            self.work_edit.setText(path)

    # -- drag and drop -----------------------------------------------------

    def accept_file(self, path):
        """Put a dropped file in whichever field it belongs to.

        Extension decides: media goes to the media field, a known scene
        extension to the work file field. Anything else fills whichever field
        is still empty, media first, because publishing the media is the point
        of the dialog.
        """
        if is_media(path):
            self.file_edit.setText(path)
        elif is_workfile(path):
            self.work_edit.setText(path)
        elif not self.path:
            self.file_edit.setText(path)
        else:
            self.work_edit.setText(path)

    def dragEnterEvent(self, event):
        if dropped_files(event.mimeData()):
            event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        files = dropped_files(event.mimeData())
        if not files:
            return
        event.acceptProposedAction()
        # Two files at once is the common "media + scene" drag, so honour both
        # rather than making the artist drop twice.
        for path in files[:2]:
            self.accept_file(path)

    # -- field changes -----------------------------------------------------

    def _on_path_typed(self, text):
        self.path = text.strip()
        self.media_info = None
        valid = bool(self.path) and os.path.isfile(self.path)
        self._refresh_publish_enabled()

        if not self.path:
            self.file_info.setText("")
            self._show_message("Drop a file here")
            return
        if not valid:
            self.file_info.setText("")
            self._show_message("File not found")
            return
        if not is_media(self.path):
            ext = os.path.splitext(self.path)[1] or "this file"
            self.file_info.setText(f"{ext} is not a publishable media format")
            self._show_message("Not a media file")
            return

        self.file_info.setText(
            f"{os.path.basename(self.path)}\nReading media…")
        self.file_info.setToolTip(self.path)
        self._load_preview()
        self._start_inspect()

    def _start_inspect(self):
        job = _InspectJob(self.path)
        job.signals.done.connect(self._on_inspected)
        job.signals.failed.connect(
            lambda e: self.file_info.setText(
                f"{os.path.basename(self.path)}\n{e}"))
        self._inspect = job
        QThreadPool.globalInstance().start(job)

    def _on_inspected(self, info):
        if info.path != self.path:
            return                      # a newer file was chosen meanwhile
        self.media_info = info
        self.file_info.setText(f"{os.path.basename(info.path)}\n"
                               f"{info.summary()}")
        if info.error:
            log.info("media inspection limited for %s: %s",
                     info.path, info.error)

    def _on_work_typed(self, text):
        self.work_path = text.strip()
        self.work_clear.setVisible(bool(self.work_path))
        self._refresh_publish_enabled()

        if not self.work_path:
            self.work_info.setText("")
            return
        if not os.path.isfile(self.work_path):
            self.work_info.setText("Scene file not found")
            return

        ext = os.path.splitext(self.work_path)[1].lower()
        kind = config.WORKFILE_EXTENSIONS.get(ext, "Scene file")
        size = human_size(os.path.getsize(self.work_path))
        self.work_info.setText(
            f"{kind}  ·  {size}\n{os.path.basename(self.work_path)}")
        self.work_info.setToolTip(self.work_path)

    def _refresh_publish_enabled(self):
        """Media must exist and be a media format; a named work file must
        exist too; the name must not already be taken."""
        if self.published:
            self.publish_btn.setEnabled(False)
            return
        ok = bool(self.path) and os.path.isfile(self.path) \
            and is_media(self.path)
        if self.work_path and not os.path.isfile(self.work_path):
            ok = False
        if self.name_warning.isVisible():
            ok = False
        self.publish_btn.setEnabled(ok)

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
        self.preview.setObjectName("dropHint")
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
        if not self._check_name():
            return
        request = publish_service.PublishRequest(
            self.project, self.task, self.name_edit.text(), self.path,
            self.desc_edit.toPlainText(), self.work_path)

        # Everything the service would refuse anyway, refused here first so the
        # artist gets the message beside the field rather than in a dialog.
        try:
            self.service.validate_context(self.project, self.task)
            self.service.inspect_media(self.path)
        except publish_service.PublishError as e:
            self.status.setText(str(e))
            return

        self._set_busy(True)
        job = _PublishJob(self.service, request)
        job.signals.progress.connect(self._on_stage)
        job.signals.done.connect(self._on_done)
        job.signals.failed.connect(self._on_failed)
        self._job = job                    # keep the wrapper alive
        QThreadPool.globalInstance().start(job)

    def _on_stage(self, text):
        self.status.setObjectName("tileSub")
        self.status.setText(text)
        self._restyle(self.status)

    def _on_cancel(self):
        """Cancel means two different things depending on the stage."""
        if self._job is not None and not self.published:
            self._job.cancel()
            self.status.setText(
                "Cancelling — waiting for the current step to finish…")
            self.cancel_btn.setEnabled(False)
            return
        self.reject()

    def _set_busy(self, busy):
        # The bar stays indeterminate on purpose: shotgun_api3.upload() offers
        # no progress callback, so a percentage would be invented. The stage
        # line carries the file size instead.
        self.progress.setVisible(busy)
        self.publish_btn.setEnabled(not busy and not self.published)
        self.file_edit.setEnabled(not busy)
        self.work_edit.setEnabled(not busy)
        self.name_edit.setEnabled(not busy)
        self.desc_edit.setEnabled(not busy)
        self.setAcceptDrops(not busy)
        self.preview_host.setAcceptDrops(not busy)
        self.cancel_btn.setEnabled(True)

    def _on_done(self, result):
        self.published = result
        self._set_busy(False)
        self.progress.hide()
        log.info("published Version %s (%s) for task %s",
                 result.id, result.code, self.task["id"])
        self.result_page.show_result(result)
        self.pages.setCurrentWidget(self.result_page)

    def _on_failed(self, error):
        self._set_busy(False)
        self._refresh_publish_enabled()
        self.progress.hide()
        if isinstance(error, publish_service.PublishCancelled):
            self.status.setObjectName("tileSub")
            self.status.setText(str(error))
            self._restyle(self.status)
            return

        # Shown in the dialog rather than in a message box on top of it: the
        # fields the artist has to fix are right here. The raw API text stays
        # in the log, where a pipeline TD will look for it.
        title = getattr(error, "title", "Publish failed")
        self.status.setObjectName("errorText")
        self.status.setText(f"{title}\n{error}")
        self._restyle(self.status)

    @staticmethod
    def _restyle(widget):
        """objectName drives the colour, so the style has to be re-applied."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def closeEvent(self, event):
        if self.player is not None:
            self.player.stop()
        if self._job is not None and not self.published:
            self._job.cancel()
        super().closeEvent(event)


class _ResultPage(QFrame):
    """What was published, and how to go look at it."""

    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.result = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.heading = QLabel("Publish Successful")
        self.heading.setObjectName("headerTitle")
        lay.addWidget(self.heading)

        card = QFrame()
        card.setObjectName("tile")
        self.grid = QGridLayout(card)
        self.grid.setContentsMargins(14, 12, 14, 12)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        lay.addWidget(card)

        self.note = QLabel("")
        self.note.setObjectName("warnText")
        self.note.setWordWrap(True)
        self.note.hide()
        lay.addWidget(self.note)
        lay.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.open_btn = QPushButton("Open Version")
        self.open_btn.setObjectName("consoleBtn")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self._open)
        buttons.addWidget(self.open_btn)

        close = QPushButton("Close")
        close.setObjectName("termBtn")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(dialog.accept)
        buttons.addWidget(close)
        lay.addLayout(buttons)

    def show_result(self, result):
        self.result = result
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        task = self.dialog.task
        info = result.media_info
        rows = [
            ("Version", result.code),
            ("Task", task.get("content", "")),
            ("Media", os.path.basename(info.path) if info else ""),
            ("Media details", info.summary() if info else ""),
            ("Published using", self.dialog.sg.api_identity),
            ("Credited to", self.dialog.user_email),
            ("Took", f"{result.elapsed:.0f}s"),
        ]
        if result.work_file_note:
            rows.append(("Work file", result.work_file_note))
        for r, (key, value) in enumerate(v for v in rows if v[1]):
            k = QLabel(key)
            k.setObjectName("tileSub")
            val = QLabel(str(value))
            val.setObjectName("tileName")
            val.setWordWrap(True)
            self.grid.addWidget(k, r, 0, Qt.AlignRight | Qt.AlignTop)
            self.grid.addWidget(val, r, 1)

        if result.work_file_error:
            self.note.setText(
                f"The Version is published, but the scene file was not "
                f"registered: {result.work_file_error}")
            self.note.show()
        else:
            self.note.hide()

    def _open(self):
        if not self.result:
            return
        try:
            paths.open_url(self.result.url)
        except Exception as e:
            log.warning("could not open %s: %s", self.result.url, e)
            QMessageBox.information(
                self, "Open Version",
                f"Could not open a browser here.\n\n{self.result.url}")


def _sub(text):
    lbl = QLabel(text)
    lbl.setObjectName("tileSub")
    return lbl
