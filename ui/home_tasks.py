"""The artist's open tasks, on the home page, across every project.

The first question an artist has when Flow opens is "what am I working on".
This answers it without picking a project first. Double-clicking a task opens
its project and lands on the task, the same place the header search goes.
Right-click gives the same task menu as the project page (TaskMenu), acting on
the task's own project, so there is no second copy of those actions.

"Open" means any status not in config.TASK_DONE_STATUSES. That filter runs on
the server, so finished work never crosses the wire. The filters on this page
run in memory over the list that came back.
"""

import datetime

import config

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import theme
from .branding import LoadingPage
from .software_page import TaskMenu
from .widgets import DueDate, EmptyState, StatusPill

ALL = ""

# (key, label) for the due filter.
DUE_CHOICES = [
    (ALL, "Any due date"),
    ("overdue", "Overdue"),
    ("week", "Due within 7 days"),
    ("none", "No due date"),
]


def _due_matches(task, due, today):
    raw = task.get("due_date") or ""
    if due == "none":
        return not raw
    if not raw:
        return False
    try:
        date = datetime.date.fromisoformat(raw)
    except ValueError:
        return False
    if due == "overdue":
        return date < today
    if due == "week":
        return date <= today + datetime.timedelta(days=7)
    return True


def filter_tasks(tasks, text="", project_id=None, step=ALL, status=ALL,
                 due=ALL, today=None):
    """The tasks that pass every filter. Words in `text` may come in any order."""
    today = today or datetime.date.today()
    words = text.lower().split()
    out = []
    for t in tasks:
        if project_id is not None and \
                (t.get("project") or {}).get("id") != project_id:
            continue
        if step and (t.get("step") or {}).get("name") != step:
            continue
        if status and t.get("sg_status_list") != status:
            continue
        if due and not _due_matches(t, due, today):
            continue
        if words:
            hay = " ".join(str(v) for v in (
                t.get("content"), (t.get("entity") or {}).get("name"),
                (t.get("project") or {}).get("name"),
                (t.get("step") or {}).get("name"),
                t.get("sg_status_list"))).lower()
            if not all(w in hay for w in words):
                continue
        out.append(t)
    return out


class HomeTasks(TaskMenu, QWidget):
    COLS = ["Task", "Link", "Project", "Step", "Status", "Due"]
    COL_STATUS = 4
    COL_DUE = 5

    task_opened = Signal(object)          # the Task dict
    refresh_requested = Signal()
    # The task menu's actions, as on the project page's TasksTable.
    package_launched = Signal(object, str, str)
    folder_requested = Signal(str)
    latest_version_requested = Signal(object, object)
    status_change_requested = Signal(object, str)
    publish_requested = Signal(object)
    versions_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self._tasks = []
        self._rows = []
        self._status_labels = {}
        self._loading = False
        self._projects = {}          # id -> full Project dict, for folders
        self._statuses = []          # [(code, label), ...] for TaskMenu
        self._latest = {}            # task id -> newest Version
        self._attention = {}         # the review dots are project-page only
        self._packages = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 8)
        lay.setSpacing(10)

        top = QHBoxLayout()
        heading = QLabel("My Open Tasks")
        heading.setObjectName("headerTitle")
        top.addWidget(heading)
        self.count = QLabel("")
        self.count.setObjectName("tileSub")
        top.addWidget(self.count)
        top.addStretch()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("termBtn")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_requested)
        top.addWidget(self.refresh_btn)
        lay.addLayout(top)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter tasks")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self._rebuild)
        filters.addWidget(self.search)
        self.project_box = self._combo(filters)
        self.step_box = self._combo(filters)
        self.status_box = self._combo(filters)
        self.due_box = self._combo(filters)
        for key, label in DUE_CHOICES:
            self.due_box.addItem(label, key)
        filters.addStretch()
        hint = QLabel("Double-click to open a task, right-click for actions")
        hint.setObjectName("tileSub")
        filters.addWidget(hint)
        lay.addLayout(filters)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.Fixed)
        header.setSectionResizeMode(self.COL_DUE, QHeaderView.Fixed)
        header.resizeSection(self.COL_STATUS, 110)
        header.resizeSection(self.COL_DUE, 110)
        header.setHighlightSections(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setMouseTracking(True)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setItemDelegateForColumn(self.COL_STATUS,
                                            StatusPill(self.table))
        self.table.setItemDelegateForColumn(self.COL_DUE, DueDate(self.table))
        self.table.cellDoubleClicked.connect(self._open_row)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.stack.addWidget(self.table)

        self.empty = EmptyState(
            "✓", "No open tasks",
            "Nothing assigned to you is still in progress, or the filters "
            "hide it.")
        self.stack.addWidget(self.empty)

        self.loading = LoadingPage("Loading your tasks...")
        self.stack.addWidget(self.loading)

        # Connected last: filling the due choices above would otherwise
        # rebuild a table that does not exist yet.
        for box in (self.project_box, self.step_box, self.status_box,
                    self.due_box):
            box.currentIndexChanged.connect(self._rebuild)

    def _combo(self, row):
        box = QComboBox()
        box.setMinimumWidth(130)
        row.addWidget(box)
        return box

    # -- data ---------------------------------------------------------------

    def set_loading(self):
        self._loading = True
        if not self._tasks:
            self.stack.setCurrentWidget(self.loading)

    def set_statuses(self, statuses):
        self._statuses = statuses or []
        self._status_labels = dict(self._statuses)
        self._fill_choices()

    def set_projects(self, projects):
        self._projects = {p["id"]: p for p in projects or []}

    def _menu_project(self, task):
        """The task's full project: folder paths need its tank_name."""
        link = task.get("project") or {}
        return self._projects.get(link.get("id")) or (link or None)

    def update_task(self, task_id, code):
        """A status write from the menu. Finished tasks leave the list."""
        if code in config.TASK_DONE_STATUSES:
            self._tasks = [t for t in self._tasks if t["id"] != task_id]
            self._rebuild()
            return
        super().update_task(task_id, code)

    def set_tasks(self, tasks):
        self._tasks = tasks
        self._loading = False
        self._fill_choices()
        self._rebuild()

    def _fill_choices(self):
        """Offer only values the artist's own tasks have, and keep the pick."""
        projects = {}
        steps, statuses = set(), set()
        for t in self._tasks:
            p = t.get("project") or {}
            if p.get("id") is not None:
                projects[p["id"]] = p.get("name") or str(p["id"])
            if (t.get("step") or {}).get("name"):
                steps.add(t["step"]["name"])
            if t.get("sg_status_list"):
                statuses.add(t["sg_status_list"])

        self._refill(self.project_box, "All projects",
                     sorted(((n, i) for i, n in projects.items()),
                            key=lambda x: x[0].lower()), none=None)
        self._refill(self.step_box, "All steps",
                     [(s, s) for s in sorted(steps)])
        self._refill(self.status_box, "All statuses",
                     [(self._status_labels.get(c, c), c)
                      for c in sorted(statuses)])

    def _refill(self, box, all_label, choices, none=ALL):
        current = box.currentData()
        box.blockSignals(True)
        box.clear()
        box.addItem(all_label, none)
        for label, data in choices:
            box.addItem(label, data)
        index = box.findData(current)
        box.setCurrentIndex(index if index >= 0 else 0)
        box.blockSignals(False)

    # -- view ---------------------------------------------------------------

    def _rebuild(self):
        self._rows = filter_tasks(
            self._tasks, self.search.text(),
            project_id=self.project_box.currentData(),
            step=self.step_box.currentData() or ALL,
            status=self.status_box.currentData() or ALL,
            due=self.due_box.currentData() or ALL)

        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self._rows))
        for r, t in enumerate(self._rows):
            values = [
                t.get("content") or "",
                (t.get("entity") or {}).get("name", ""),
                (t.get("project") or {}).get("name", ""),
                (t.get("step") or {}).get("name", ""),
                t.get("sg_status_list") or "",
                t.get("due_date") or "",
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if c in (2, 3):
                    item.setForeground(QColor(theme.TEXT_DIM))
                if c == self.COL_STATUS:
                    item.setToolTip(self._status_labels.get(v, v))
                self.table.setItem(r, c, item)
        self.table.setUpdatesEnabled(True)

        total, shown = len(self._tasks), len(self._rows)
        self.count.setText(f"{shown} of {total}" if shown != total
                           else (str(total) if total else ""))
        if self._loading and not self._tasks:
            return
        self.stack.setCurrentWidget(self.table if shown else self.empty)

    def _open_row(self, row, _col=0):
        if 0 <= row < len(self._rows):
            self.task_opened.emit(self._rows[row])
