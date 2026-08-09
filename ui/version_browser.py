"""Browse the Versions already published on a shot or asset.

Every filter is a ShotGrid query, not a pass over a list held in memory: the
browser fetches a page at a time and asks the server to do the narrowing. The
filter building itself lives in `version_query`, which has no Qt in it and can
be tested on its own.
"""

import datetime
import os

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame, QStackedWidget, QSplitter, QMenu, QApplication,
    QMessageBox, QSizePolicy,
)

import applog
import config
import paths
import version_query
from . import jobs, theme
from .widgets import EmptyState, StatusPill, load_thumbnail

log = applog.get()

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAVE_MULTIMEDIA = True
except ImportError:                                  # pragma: no cover
    HAVE_MULTIMEDIA = False

PREVIEW_SIZE = (360, 202)


def _name_of(entity):
    if not entity:
        return ""
    return entity.get("name") or entity.get("code") or ""


def _when(value):
    """ShotGrid datetimes shown the way a production board would."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    now = datetime.datetime.now(value.tzinfo) if value.tzinfo else \
        datetime.datetime.now()
    if value.date() == now.date():
        return f"Today {value:%H:%M}"
    if (now.date() - value.date()).days == 1:
        return f"Yesterday {value:%H:%M}"
    return f"{value:%d %b %Y %H:%M}"


class VersionBrowser(QDialog):
    """Versions for a task's entity, filtered the way a supervisor asks."""

    def __init__(self, sg, project, task, parent=None):
        super().__init__(parent)
        self.sg = sg
        self.project = project
        self.task = task
        self.entity = task.get("entity") or {}

        self._versions = []
        self._page = 1
        self._more = False
        self._request = 0            # so a slow reply cannot overwrite a fast one
        self.error = ""              # last query failure, shown in place
        self._jobs = set()
        self._player = None
        self._options_locked = False  # option lists come from the first, unfiltered page

        step = (task.get("step") or {}).get("name", "")
        self.setWindowTitle(
            f"Versions — {_name_of(self.entity) or project['name']}"
            + (f" / {step}" if step else ""))
        self.setStyleSheet(theme.STYLE)
        self.resize(1080, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        root.addWidget(self._header())
        root.addWidget(self._filters())

        split = QSplitter(Qt.Vertical)
        split.addWidget(self._table_side())
        split.addWidget(self._details_side())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setHandleWidth(1)
        root.addWidget(split, 1)

        buttons = QHBoxLayout()
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("tileSub")
        buttons.addWidget(self.count_lbl)
        buttons.addStretch()

        self.more_btn = QPushButton("Load more")
        self.more_btn.setObjectName("consoleBtn")
        self.more_btn.clicked.connect(self._load_more)
        self.more_btn.hide()
        buttons.addWidget(self.more_btn)

        close = QPushButton("Close")
        close.setObjectName("termBtn")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(config.SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self.reload)

        self._load_reference_data()
        self.reload()

    # -- construction ------------------------------------------------------

    def _header(self):
        bar = QFrame()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)

        title = QLabel(self.windowTitle())
        title.setObjectName("headerTitle")
        lay.addWidget(title)
        lay.addStretch()

        self.scope = QComboBox()
        self.scope.addItem(f"All tasks on {_name_of(self.entity) or 'entity'}",
                           "entity")
        self.scope.addItem(f"This task only ({self.task.get('content', '')})",
                           "task")
        self.scope.currentIndexChanged.connect(self.reload)
        lay.addWidget(self.scope)
        return bar

    def _filters(self):
        bar = QFrame()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search name, description, artist, task or shot")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(300)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        lay.addWidget(self.search)

        self.dept = self._combo(lay, "Department")
        self.user = self._combo(lay, "User")
        self.status = self._combo(lay, "Status")
        self.date = self._combo(lay, "Date")
        for key, label in version_query.DATE_RANGES:
            self.date.addItem(label, key)

        self.sort = self._combo(lay, "Sort")
        for key, label, _order in version_query.SORT_ORDERS:
            self.sort.addItem(label, key)
        self.sort.setCurrentIndex(
            [k for k, _l, _o in version_query.SORT_ORDERS]
            .index(version_query.DEFAULT_SORT))

        lay.addStretch()
        return bar

    def _combo(self, layout, label):
        box = QVBoxLayout()
        box.setSpacing(2)
        lbl = QLabel(label)
        lbl.setObjectName("filterLabel")
        box.addWidget(lbl)
        combo = QComboBox()
        combo.setMinimumWidth(140)
        combo.addItem("All", None)
        combo.currentIndexChanged.connect(self.reload)
        box.addWidget(combo)
        layout.addLayout(box)
        return combo

    def _table_side(self):
        host = QFrame()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Version", "Department", "User", "Status", "Date"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(3, 110)
        header.resizeSection(4, 170)
        header.setHighlightSections(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setMouseTracking(True)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setItemDelegateForColumn(3, StatusPill(self.table))
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.itemSelectionChanged.connect(self._on_selected)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.stack.addWidget(self.table)

        self.empty = EmptyState(
            "▤", "No versions match",
            "Nothing has been published against this entity with these "
            "filters. Clear the filters, or widen the scope above.")
        self.stack.addWidget(self.empty)

        self.loading = EmptyState("◔", "Loading versions…", "")
        self.stack.addWidget(self.loading)
        self.stack.setCurrentWidget(self.loading)
        return host

    def _details_side(self):
        host = QFrame()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(16)

        self.preview_host = QFrame()
        self.preview_host.setObjectName("tile")
        self.preview_host.setFixedSize(*PREVIEW_SIZE)
        preview_lay = QVBoxLayout(self.preview_host)
        preview_lay.setContentsMargins(1, 1, 1, 1)
        self.preview = QLabel("Select a version")
        self.preview.setObjectName("dropHint")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        preview_lay.addWidget(self.preview)
        lay.addWidget(self.preview_host, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.details = QGridLayout()
        self.details.setHorizontalSpacing(18)
        self.details.setVerticalSpacing(4)
        self.details.setColumnStretch(1, 1)
        right.addLayout(self.details)
        right.addStretch()

        actions = QHBoxLayout()
        actions.addStretch()
        self.play_btn = QPushButton("Play")
        self.play_btn.setObjectName("consoleBtn")
        self.play_btn.clicked.connect(self._play)
        self.play_btn.hide()
        actions.addWidget(self.play_btn)

        self.open_btn = QPushButton("Open in ShotGrid")
        self.open_btn.setObjectName("consoleBtn")
        self.open_btn.clicked.connect(self._open_in_shotgrid)
        self.open_btn.setEnabled(False)
        actions.addWidget(self.open_btn)
        right.addLayout(actions)

        lay.addLayout(right, 1)
        return host

    # -- reference data ----------------------------------------------------

    def _load_reference_data(self):
        """Departments and statuses come from ShotGrid's own schema.

        Both are cached on the client for the session, so opening the browser
        twice does not ask twice.
        """
        jobs.run(self._jobs, self.sg.steps, self._on_steps,
                 on_error=lambda m: log.warning("no Step list: %s", m))
        jobs.run(self._jobs, self.sg.version_statuses, self._on_statuses,
                 on_error=lambda m: log.warning("no Version statuses: %s", m))

    def _on_steps(self, steps):
        entity_type = self.entity.get("type")
        for step in steps or []:
            # Steps are per entity type; a Shot browser has no use for the
            # Asset modelling steps.
            if entity_type and step.get("entity_type") not in (None, "",
                                                               entity_type):
                continue
            self.dept.addItem(step.get("code") or step.get("short_name") or
                              f"Step {step['id']}", step)

    def _on_statuses(self, statuses):
        for code, label in statuses or []:
            self.status.addItem(f"{label}", code)

    # -- querying ----------------------------------------------------------

    def _current_filters(self):
        return version_query.build_filters(
            search=self.search.text(),
            step=self.dept.currentData(),
            user=self.user.currentData(),
            status=self.status.currentData() or "",
            date_key=self.date.currentData() or "all",
        )

    def reload(self):
        self._page = 1
        self._versions = []
        self.error = ""
        self.table.setRowCount(0)
        self.count_lbl.setObjectName("tileSub")
        self.count_lbl.style().unpolish(self.count_lbl)
        self.count_lbl.style().polish(self.count_lbl)
        self.stack.setCurrentWidget(self.loading)
        self._fetch()

    def _load_more(self):
        self._page += 1
        self._fetch()

    def _fetch(self):
        self._request += 1
        request = self._request
        by_task = self.scope.currentData() == "task"
        filters = self._current_filters()
        order = version_query.order_for(self.sort.currentData())
        limit = config.VERSION_PAGE_SIZE
        page = self._page

        self.more_btn.setEnabled(False)

        def query():
            return self.sg.versions(
                entity=None if by_task else (self.entity or None),
                task_id=self.task["id"] if by_task else None,
                filters=filters, order=order, limit=limit, page=page)

        def done(rows):
            if request != self._request:
                return              # a newer query already answered
            self._on_versions(rows)

        def failed(message):
            if request != self._request:
                return
            # Shown in the browser rather than in a message box: the filters
            # that produced it are on screen and may be what needs changing.
            log.error("could not list versions: %s", message)
            self.error = message
            self.count_lbl.setObjectName("errorText")
            self.count_lbl.setText(f"ShotGrid did not return the versions: "
                                   f"{message}")
            self.count_lbl.style().unpolish(self.count_lbl)
            self.count_lbl.style().polish(self.count_lbl)
            self.more_btn.hide()
            self.stack.setCurrentWidget(self.empty)

        jobs.run(self._jobs, query, done, on_error=failed)

    def _on_versions(self, rows):
        rows = rows or []
        self._more = len(rows) == config.VERSION_PAGE_SIZE
        self._versions.extend(rows)
        self._fill_table()

        # The artist list is whoever appears in the data; locking it after the
        # first page keeps the dropdown from shuffling under the mouse.
        if not self._options_locked and rows:
            for user in version_query.options_from(rows)["users"]:
                self.user.addItem(_name_of(user) or f"User {user['id']}", user)
            self._options_locked = True

        self.more_btn.setVisible(self._more)
        self.more_btn.setEnabled(True)
        total = len(self._versions)
        self.count_lbl.setText(
            f"{total} version{'s' if total != 1 else ''}"
            + (" (more available)" if self._more else ""))
        self.stack.setCurrentWidget(self.table if total else self.empty)

    def _fill_table(self):
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        for v in self._versions:
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [
                v.get("code") or f"Version {v['id']}",
                _name_of(v.get("sg_task.Task.step")),
                _name_of(v.get("user") or v.get("created_by")),
                v.get("sg_status_list") or "",
                _when(v.get("created_at")),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if c == 0:
                    item.setForeground(QColor(theme.TEXT))
                elif c in (1, 2, 4):
                    item.setForeground(QColor(theme.TEXT_DIM))
                self.table.setItem(r, c, item)
        self.table.setUpdatesEnabled(True)

    # -- selection ---------------------------------------------------------

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        r = rows[0].row()
        return self._versions[r] if r < len(self._versions) else None

    def _on_selected(self):
        version = self._selected()
        self.open_btn.setEnabled(bool(version))
        if not version:
            return
        self._show_details(version)
        self._show_preview(version)

    def _show_details(self, version):
        while self.details.count():
            item = self.details.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        task = version.get("sg_task") or {}
        rows = [
            ("Version", version.get("code")),
            ("Version ID", version["id"]),
            ("Entity", _name_of(version.get("entity"))),
            ("Task", _name_of(task) or version.get("sg_task.Task.content")),
            ("Department", _name_of(version.get("sg_task.Task.step"))),
            ("Created by", _name_of(version.get("user") or
                                    version.get("created_by"))),
            ("Created at", _when(version.get("created_at"))),
            ("Updated at", _when(version.get("updated_at"))),
            ("Status", version.get("sg_status_list")),
            ("Frame range", version.get("frame_range")),
            ("Frames", version.get("frame_count")),
            ("Media path", version.get("sg_path_to_movie") or
                           version.get("sg_path_to_frames")),
            ("Description", version.get("description")),
        ]
        # Only what this site actually filled in: assuming every ShotGrid has
        # every field is how a tool ends up showing a column of dashes.
        r = 0
        for key, value in rows:
            if value in (None, "", []):
                continue
            k = QLabel(key)
            k.setObjectName("tileSub")
            v = QLabel(str(value))
            v.setObjectName("tileName")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.details.addWidget(k, r, 0, Qt.AlignRight | Qt.AlignTop)
            self.details.addWidget(v, r, 1)
            r += 1

    def _show_preview(self, version):
        self._stop_player()
        local = version.get("sg_path_to_movie") or ""
        self.play_btn.setVisible(
            bool(HAVE_MULTIMEDIA and local and os.path.isfile(local)))

        url = (version.get("image") or "")
        if not url:
            self._preview_message("No thumbnail on this version")
            return
        self._preview_message("Loading preview…")
        target = version["id"]

        def show(pixmap):
            current = self._selected()
            if not current or current["id"] != target or pixmap.isNull():
                return
            self._clear_preview()
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setPixmap(pixmap.scaled(
                PREVIEW_SIZE[0] - 2, PREVIEW_SIZE[1] - 2,
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.preview = label
            self.preview_host.layout().addWidget(label)

        load_thumbnail(url, show)

    def _clear_preview(self):
        layout = self.preview_host.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _preview_message(self, text):
        self._clear_preview()
        self.preview = QLabel(text)
        self.preview.setObjectName("dropHint")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview_host.layout().addWidget(self.preview)

    def _play(self):
        """Play the version from disk, where the render actually lives.

        Streaming ShotGrid's own copy would need the media URL and its auth;
        the path on /jobs is right there and plays without a round trip.
        """
        version = self._selected()
        if not version or not HAVE_MULTIMEDIA:
            return
        path = version.get("sg_path_to_movie") or ""
        if not os.path.isfile(path):
            QMessageBox.information(self, "Play",
                                    f"The media is not readable here:\n{path}")
            return

        self._clear_preview()
        video = QVideoWidget()
        video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_host.layout().addWidget(video)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(video)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _stop_player(self):
        if self._player is not None:
            self._player.stop()
            self._player = None

    # -- actions -----------------------------------------------------------

    def _context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid() or index.row() >= len(self._versions):
            return
        self.table.selectRow(index.row())
        version = self._versions[index.row()]

        menu = QMenu(self)
        open_act = QAction("Open in ShotGrid", menu)
        open_act.triggered.connect(self._open_in_shotgrid)
        menu.addAction(open_act)

        path = version.get("sg_path_to_movie") or \
            version.get("sg_path_to_frames") or ""
        copy = QAction("Copy media path", menu)
        copy.setEnabled(bool(path))
        copy.triggered.connect(
            lambda _=False, p=path: QApplication.clipboard().setText(p))
        menu.addAction(copy)

        copy_name = QAction("Copy version name", menu)
        copy_name.triggered.connect(
            lambda _=False, n=version.get("code") or "":
            QApplication.clipboard().setText(n))
        menu.addAction(copy_name)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_in_shotgrid(self):
        version = self._selected()
        if not version:
            return
        url = config.entity_url("Version", version["id"])
        try:
            paths.open_url(url)
        except Exception as e:
            log.warning("could not open %s: %s", url, e)
            QMessageBox.information(self, "Open in ShotGrid",
                                    f"Could not open a browser here.\n\n{url}")

    def closeEvent(self, event):
        self._stop_player()
        super().closeEvent(event)
