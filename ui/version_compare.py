"""Compare two Versions: the pixels, and the feedback that caused them.

Any two versions, not just adjacent ones. Four modes -- side by side, A/B,
wipe, and difference -- with difference offered only where it means something:
two stills of the same resolution. A movie has no meaningful abs(A - B) frame
without a frame-accurate sync this does not pretend to have, so movies get the
reliable A/B workflow instead of a fragile custom player.

Media comes from whatever the Version has that this machine can read: the
local path first, the ShotGrid thumbnail second.
"""

import os

from PySide6.QtCore import Qt, QUrl, QPointF, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QComboBox, QStackedWidget, QSlider, QSizePolicy, QScrollArea,
    QWidget, QButtonGroup, QMessageBox,
)

import applog
import config
import media_inspector
import notes_service
from . import jobs, theme
from .widgets import EmptyState, load_thumbnail

log = applog.get()

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAVE_MULTIMEDIA = True
except ImportError:                                  # pragma: no cover
    HAVE_MULTIMEDIA = False

SIDE_BY_SIDE, AB, WIPE, DIFFERENCE = "side", "ab", "wipe", "difference"


def local_media(version):
    """The version's media on this machine, if it is reachable."""
    for field in ("sg_path_to_movie", "sg_path_to_frames"):
        path = version.get(field) or ""
        if path and os.path.isfile(path):
            return path
    return ""


def is_movie(version):
    path = local_media(version)
    return config.media_kind(path) == "movie" if path else False


class VersionMedia:
    """One side of the comparison, and what it managed to load."""

    def __init__(self, version):
        self.version = version
        self.path = local_media(version)
        self.pixmap = QPixmap()
        self.info = media_inspector.inspect(self.path) if self.path else None
        self.error = ""

        if self.path and config.media_kind(self.path) == "image":
            self.pixmap = QPixmap(self.path)
            if self.pixmap.isNull():
                self.error = (f"Qt has no reader for "
                              f"{os.path.splitext(self.path)[1]} files")
        elif not self.path:
            self.error = "No media readable from this machine"

    @property
    def code(self):
        return self.version.get("code") or f"Version {self.version['id']}"

    @property
    def resolution(self):
        if not self.pixmap.isNull():
            return f"{self.pixmap.width()} × {self.pixmap.height()}"
        if self.info and self.info.resolution:
            return self.info.resolution
        return ""

    @property
    def comparable_image(self):
        return not self.pixmap.isNull()


class ImageCompare(QWidget):
    """Both stills, in whichever mode is selected, sharing zoom and pan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.a = self.b = None
        self.mode = SIDE_BY_SIDE
        self.zoom = 1.0
        self.fit = True
        self.wipe = 0.5
        self.showing_b = False
        self.setMinimumHeight(280)

    def set_media(self, a, b):
        self.a, self.b = a, b
        self.update()

    def set_mode(self, mode):
        self.mode = mode
        self.update()

    def set_wipe(self, value):
        self.wipe = max(0.0, min(1.0, value))
        self.update()

    def toggle(self):
        self.showing_b = not self.showing_b
        self.update()

    def set_zoom(self, zoom):
        self.fit = False
        self.zoom = max(0.05, min(8.0, zoom))
        self.update()

    def fit_to_window(self):
        self.fit = True
        self.update()

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.SURFACE_SUNK))
        if not self.a or not self.b:
            return

        if self.mode == SIDE_BY_SIDE:
            half = self.width() // 2
            self._draw(painter, self.a, self.rect().adjusted(0, 0, -half, 0))
            self._draw(painter, self.b, self.rect().adjusted(half, 0, 0, 0))
            painter.fillRect(half - 1, 0, 2, self.height(),
                             QColor(theme.BORDER))
            return

        if self.mode == AB:
            self._draw(painter, self.b if self.showing_b else self.a,
                       self.rect())
            return

        if self.mode == WIPE:
            split = int(self.width() * self.wipe)
            painter.save()
            painter.setClipRect(0, 0, split, self.height())
            self._draw(painter, self.a, self.rect())
            painter.restore()
            painter.save()
            painter.setClipRect(split, 0, self.width() - split, self.height())
            self._draw(painter, self.b, self.rect())
            painter.restore()
            painter.fillRect(split - 1, 0, 2, self.height(),
                             QColor(theme.ACCENT))
            return

        if self.mode == DIFFERENCE:
            diff = self._difference()
            if diff is None:
                return
            self._draw_pixmap(painter, diff, self.rect())

    def _draw(self, painter, media, rect):
        if media.comparable_image:
            self._draw_pixmap(painter, media.pixmap, rect)
            return
        painter.setPen(QColor(theme.TEXT_FAINT))
        painter.drawText(rect, Qt.AlignCenter,
                         media.error or "No preview")

    def _draw_pixmap(self, painter, pixmap, rect):
        if self.fit:
            scaled = pixmap.scaled(rect.size(), Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
        else:
            scaled = pixmap.scaled(pixmap.size() * self.zoom,
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
        # Same rectangle for both sides, so a zoom or a pan lines up.
        x = rect.x() + (rect.width() - scaled.width()) // 2
        y = rect.y() + (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def _difference(self):
        """abs(A - B), which only means anything at a shared resolution.

        Done with Qt's own Difference composition rather than a per-pixel
        loop: two 2K frames is four million pixels, and in Python that is a
        frozen window rather than a comparison.
        """
        if not (self.a.comparable_image and self.b.comparable_image):
            return None
        a = self.a.pixmap.toImage().convertToFormat(QImage.Format_RGB32)
        b = self.b.pixmap.toImage().convertToFormat(QImage.Format_RGB32)
        if a.size() != b.size():
            return None

        out = QImage(a)
        painter = QPainter(out)
        painter.setCompositionMode(QPainter.CompositionMode_Difference)
        painter.drawImage(0, 0, b)
        painter.end()
        return QPixmap.fromImage(out)

    def difference_available(self):
        """Why difference is or is not offered, in one place."""
        if not (self.a and self.b):
            return False, "Nothing loaded"
        if not (self.a.comparable_image and self.b.comparable_image):
            return False, "Difference needs two still images"
        if self.a.pixmap.size() != self.b.pixmap.size():
            return False, ("Difference needs matching resolutions "
                           f"({self.a.resolution} vs {self.b.resolution})")
        return True, ""


class VersionCompare(QDialog):
    """The compare window: media, modes, metadata and the notes on both."""

    def __init__(self, sg, project, version_a, version_b, versions=None,
                 parent=None):
        super().__init__(parent)
        self.sg = sg
        self.project = project
        self.notes = notes_service.NotesService(sg)
        self.versions = versions or []
        self.media_a = self.media_b = None
        self.player = None
        self._jobs = set()

        self.setWindowTitle("Version Compare")
        self.setStyleSheet(theme.STYLE)
        self.resize(1180, 780)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        heading = QLabel("Version Compare")
        heading.setObjectName("headerTitle")
        root.addWidget(heading)

        self.headers = QHBoxLayout()
        root.addLayout(self.headers)

        self.stack = QStackedWidget()
        self.image_view = ImageCompare()
        self.stack.addWidget(self.image_view)
        self.movie_view = self._movie_page()
        self.stack.addWidget(self.movie_view)
        root.addWidget(self.stack, 1)

        self.wipe_slider = QSlider(Qt.Horizontal)
        self.wipe_slider.setRange(0, 100)
        self.wipe_slider.setValue(50)
        self.wipe_slider.valueChanged.connect(
            lambda v: self.image_view.set_wipe(v / 100.0))
        self.wipe_slider.hide()
        root.addWidget(self.wipe_slider)

        root.addLayout(self._mode_bar())
        root.addWidget(self._metadata_and_notes(), 0)

        self.set_versions(version_a, version_b)

    # -- construction ------------------------------------------------------

    def _movie_page(self):
        page = QFrame()
        lay = QVBoxLayout(page)
        self.movie_host = QFrame()
        self.movie_host.setObjectName("tile")
        host_lay = QVBoxLayout(self.movie_host)
        self.movie_label = QLabel("")
        self.movie_label.setObjectName("dropHint")
        self.movie_label.setAlignment(Qt.AlignCenter)
        host_lay.addWidget(self.movie_label)
        lay.addWidget(self.movie_host, 1)

        controls = QHBoxLayout()
        controls.addStretch()
        for text, slot in (("Play", self._play), ("Pause", self._pause),
                           ("Show A", lambda: self._show_movie(False)),
                           ("Show B", lambda: self._show_movie(True))):
            button = QPushButton(text)
            button.setObjectName("consoleBtn")
            button.clicked.connect(slot)
            controls.addWidget(button)
        controls.addStretch()
        lay.addLayout(controls)

        self.movie_note = QLabel(
            "Movies compare as A/B: frame-accurate synchronised playback is "
            "not something Qt Multimedia can be relied on for here.")
        self.movie_note.setObjectName("tileSub")
        self.movie_note.setWordWrap(True)
        lay.addWidget(self.movie_note)
        return page

    def _mode_bar(self):
        bar = QHBoxLayout()
        bar.addStretch()
        self.mode_buttons = QButtonGroup(self)
        for mode, label in ((SIDE_BY_SIDE, "Side by Side"), (AB, "A/B"),
                            (WIPE, "Wipe"), (DIFFERENCE, "Difference")):
            button = QPushButton(label)
            button.setObjectName("termBtn")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, m=mode: self.set_mode(m))
            self.mode_buttons.addButton(button)
            button.setProperty("mode", mode)
            bar.addWidget(button)
        self.mode_buttons.buttons()[0].setChecked(True)

        bar.addSpacing(16)
        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setObjectName("consoleBtn")
        self.fit_btn.clicked.connect(self.image_view.fit_to_window)
        bar.addWidget(self.fit_btn)

        self.actual_btn = QPushButton("Actual size")
        self.actual_btn.setObjectName("consoleBtn")
        self.actual_btn.clicked.connect(lambda: self.image_view.set_zoom(1.0))
        bar.addWidget(self.actual_btn)
        bar.addStretch()
        return bar

    def _metadata_and_notes(self):
        host = QFrame()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        self.meta_grid = QGridLayout()
        self.meta_grid.setHorizontalSpacing(14)
        self.meta_grid.setVerticalSpacing(3)
        meta_host = QFrame()
        meta_host.setObjectName("tile")
        meta_wrap = QVBoxLayout(meta_host)
        meta_wrap.setContentsMargins(12, 8, 12, 8)
        meta_wrap.addLayout(self.meta_grid)
        lay.addWidget(meta_host, 3)

        notes_host = QFrame()
        notes_host.setObjectName("tile")
        notes_wrap = QVBoxLayout(notes_host)
        notes_wrap.setContentsMargins(12, 8, 12, 8)
        title = QLabel("Notes")
        title.setObjectName("tileName")
        notes_wrap.addWidget(title)

        self.notes_scroll = QScrollArea()
        self.notes_scroll.setWidgetResizable(True)
        self.notes_body = QWidget()
        self.notes_lay = QVBoxLayout(self.notes_body)
        self.notes_lay.setAlignment(Qt.AlignTop)
        self.notes_lay.setSpacing(4)
        self.notes_scroll.setWidget(self.notes_body)
        notes_wrap.addWidget(self.notes_scroll)
        lay.addWidget(notes_host, 2)

        host.setFixedHeight(190)
        return host

    # -- state -------------------------------------------------------------

    def set_versions(self, version_a, version_b):
        self.version_a, self.version_b = version_a, version_b
        self.media_a = VersionMedia(version_a)
        self.media_b = VersionMedia(version_b)
        self.image_view.set_media(self.media_a, self.media_b)

        self._build_headers()
        self._build_metadata()
        self._load_notes()

        movies = is_movie(version_a) or is_movie(version_b)
        self.stack.setCurrentWidget(self.movie_view if movies
                                    else self.image_view)
        if movies:
            self._show_movie(False)
        self.set_mode(AB if movies else SIDE_BY_SIDE)

    def set_mode(self, mode):
        if mode == DIFFERENCE:
            ok, why = self.image_view.difference_available()
            if not ok:
                # Refused rather than shown as black: a meaningless difference
                # image is worse than saying why there isn't one.
                QMessageBox.information(self, "Difference", why)
                self._check_button(self.image_view.mode)
                return
        self.image_view.set_mode(mode)
        self.wipe_slider.setVisible(mode == WIPE)
        self._check_button(mode)

    def _check_button(self, mode):
        for button in self.mode_buttons.buttons():
            button.setChecked(button.property("mode") == mode)

    def _build_headers(self):
        while self.headers.count():
            item = self.headers.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for label, media in (("Version A", self.media_a),
                             ("Version B", self.media_b)):
            card = QFrame()
            card.setObjectName("tile")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(2)
            side = QLabel(label)
            side.setObjectName("tileSub")
            lay.addWidget(side)
            name = QLabel(media.code)
            name.setObjectName("tileName")
            lay.addWidget(name)
            who = QLabel(_person(media.version))
            who.setObjectName("tileSub")
            lay.addWidget(who)
            self.headers.addWidget(card)

    def _build_metadata(self):
        while self.meta_grid.count():
            item = self.meta_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = [
            ("Version", self.media_a.code, self.media_b.code),
            ("User", _person(self.version_a), _person(self.version_b)),
            ("Created", _when(self.version_a.get("created_at")),
             _when(self.version_b.get("created_at"))),
            ("Status", self.version_a.get("sg_status_list") or "",
             self.version_b.get("sg_status_list") or ""),
            ("Department", _name(self.version_a.get("sg_task.Task.step")),
             _name(self.version_b.get("sg_task.Task.step"))),
            ("Description", self.version_a.get("description") or "",
             self.version_b.get("description") or ""),
            ("Resolution", self.media_a.resolution, self.media_b.resolution),
            ("Frame range", self.version_a.get("frame_range") or "",
             self.version_b.get("frame_range") or ""),
            ("Duration", _duration(self.media_a), _duration(self.media_b)),
        ]

        for r, (key, left, right) in enumerate(rows):
            k = QLabel(key)
            k.setObjectName("tileSub")
            a = QLabel(str(left) or "—")
            b = QLabel(str(right) or "—")
            for widget in (a, b):
                widget.setWordWrap(True)
                widget.setObjectName("tileName")
            # A difference in the two values is the whole point of the row, so
            # it is coloured rather than left for the eye to find.
            if left and right and str(left) != str(right):
                a.setObjectName("checkWarn")
                b.setObjectName("checkWarn")
            self.meta_grid.addWidget(k, r, 0, Qt.AlignRight | Qt.AlignTop)
            self.meta_grid.addWidget(a, r, 1)
            self.meta_grid.addWidget(b, r, 2)
        self.meta_grid.setColumnStretch(1, 1)
        self.meta_grid.setColumnStretch(2, 1)

    # -- notes -------------------------------------------------------------

    def _load_notes(self):
        while self.notes_lay.count():
            item = self.notes_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.notes_lay.addWidget(QLabel("Loading notes…"))

        pair = (self.version_a, self.version_b)

        def load():
            return [(v, self.notes.threads(v["id"])) for v in pair]

        def done(results):
            while self.notes_lay.count():
                item = self.notes_lay.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            empty = True
            for version, threads in results:
                for thread in threads:
                    empty = False
                    # Every note says which version it belongs to: in a
                    # compare window that is the difference between feedback
                    # on the old cut and feedback on the new one.
                    head = QLabel(f"{thread.author_role or 'Note'} · "
                                  f"{version.get('code') or ''}")
                    head.setObjectName("tileSub")
                    self.notes_lay.addWidget(head)
                    body = QLabel(f"“{thread.content}”")
                    body.setObjectName("noteBody")
                    body.setWordWrap(True)
                    self.notes_lay.addWidget(body)
            if empty:
                self.notes_lay.addWidget(
                    EmptyState("✎", "No notes on either version", ""))

        def failed(message):
            log.warning("could not load notes for compare: %s", message)
            while self.notes_lay.count():
                item = self.notes_lay.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            label = QLabel(f"Notes unavailable: {message}")
            label.setObjectName("errorText")
            label.setWordWrap(True)
            self.notes_lay.addWidget(label)

        jobs.run(self._jobs, load, done, on_error=failed)

    # -- movies ------------------------------------------------------------

    def _show_movie(self, show_b):
        media = self.media_b if show_b else self.media_a
        self._stop()
        if not media.path or not HAVE_MULTIMEDIA:
            self.movie_label.setText(
                media.error or "Video preview needs Qt Multimedia, which is "
                               "not available here.")
            return

        layout = self.movie_host.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        video = QVideoWidget()
        video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(video)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setMuted(True)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(video)
        self.player.setSource(QUrl.fromLocalFile(media.path))
        self.player.play()

    def _play(self):
        if self.player:
            self.player.play()

    def _pause(self):
        if self.player:
            self.player.pause()

    def _stop(self):
        if self.player is not None:
            self.player.stop()
            self.player = None

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)


# -- helpers ----------------------------------------------------------------

def _name(entity):
    if not entity:
        return ""
    return entity.get("name") or entity.get("code") or ""


def _person(version):
    return _name(version.get("user") or version.get("created_by"))


def _when(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return f"{value:%d %b %Y %H:%M}"


def _duration(media):
    info = media.info
    if not info:
        return ""
    if info.frames and info.fps:
        return f"{info.frames} frames  ·  {info.frames / info.fps:.1f}s"
    if info.duration:
        return f"{info.duration:.1f}s"
    return ""
