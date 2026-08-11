"""Search every task assigned to the artist, from the header.

The project page answers "what am I working on"; this answers "where is that
one shot" without remembering which show it belongs to. Picking a result opens
the project and lands on the task, so the search is a shortcut to the same
place the artist would have clicked their way to.

The task list is fetched once, lazily, the first time the artist types — an
artist's own workload is small enough to match in memory, and matching locally
means no query per keystroke.
"""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

MAX_RESULTS = 12
DEBOUNCE_MS = 120


def _haystack(task):
    """Everything about a task worth typing into a search box."""
    return " ".join(str(part) for part in (
        task.get("content", ""),
        (task.get("entity") or {}).get("name", ""),
        (task.get("step") or {}).get("name", ""),
        (task.get("project") or {}).get("name", ""),
        task.get("sg_status_list", ""),
    ) if part).lower()


def _label(task):
    entity = (task.get("entity") or {}).get("name", "")
    step = (task.get("step") or {}).get("name", "")
    project = (task.get("project") or {}).get("name", "")
    left = " · ".join(b for b in (entity, task.get("content", ""), step) if b)
    return f"{left}     {project}" if project else left


def matches(tasks, text, limit=MAX_RESULTS):
    """Tasks matching every word in text, entity name first.

    Word-by-word rather than substring, so "ad1030 comp" finds the comp task on
    AD1030 however the two are ordered in the row.
    """
    words = text.lower().split()
    if not words:
        return []
    found = []
    for task in tasks:
        hay = _haystack(task)
        if all(w in hay for w in words):
            found.append(task)
    entity_first = [t for t in found
                    if words[0] in ((t.get("entity") or {})
                                    .get("name", "").lower())]
    rest = [t for t in found if t not in entity_first]
    return (entity_first + rest)[:limit]


class TaskSearch(QWidget):
    task_chosen = Signal(object)      # the Task dict the artist picked
    tasks_needed = Signal()           # "fetch the list, I am being typed into"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = []
        self._requested = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.edit = QLineEdit()
        self.edit.setObjectName("taskSearch")
        self.edit.setPlaceholderText("Search my tasks   (Ctrl+K)")
        self.edit.setClearButtonEnabled(True)
        self.edit.setFixedWidth(260)
        lay.addWidget(self.edit)

        # A popup window rather than a child: the header is 54px tall, so a
        # results list drawn inside it would be clipped to nothing.
        self.results = QListWidget(self)
        self.results.setWindowFlags(Qt.Popup)
        self.results.setFocusPolicy(Qt.NoFocus)
        self.results.setObjectName("searchResults")
        self.results.setMouseTracking(True)
        self.results.hide()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._refresh)

        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._on_text)
        self.edit.returnPressed.connect(self._choose_current)
        self.results.itemClicked.connect(lambda _: self._choose_current())

    # -- data --------------------------------------------------------------

    def set_tasks(self, tasks):
        self._tasks = tasks or []
        if self.edit.text():
            self._refresh()

    def has_tasks(self):
        return bool(self._tasks)

    # -- behaviour ---------------------------------------------------------

    def focus(self):
        self.edit.setFocus(Qt.ShortcutFocusReason)
        self.edit.selectAll()

    def _on_text(self, text):
        if text and not self._requested:
            # Asked for once per window, not once per keystroke.
            self._requested = True
            self.tasks_needed.emit()
        self._timer.start()

    def _refresh(self):
        text = self.edit.text().strip()
        self.results.clear()
        if not text:
            self.results.hide()
            return

        found = matches(self._tasks, text)
        if not found:
            item = QListWidgetItem(
                "Searching your tasks…" if not self._tasks
                else f"No task matches “{text}”")
            item.setFlags(Qt.NoItemFlags)
            self.results.addItem(item)
        else:
            for task in found:
                item = QListWidgetItem(_label(task))
                item.setData(Qt.UserRole, task)
                self.results.addItem(item)
            self.results.setCurrentRow(0)
        self._show_popup()

    def _show_popup(self):
        rows = max(1, min(self.results.count(), MAX_RESULTS))
        height = rows * 26 + 8
        below = self.edit.mapToGlobal(self.edit.rect().bottomLeft())
        self.results.setGeometry(below.x(), below.y() + 4,
                                 max(self.edit.width(), 380), height)
        self.results.show()

    def _choose_current(self):
        item = self.results.currentItem()
        task = item.data(Qt.UserRole) if item else None
        self.results.hide()
        if task:
            self.edit.clear()
            self.task_chosen.emit(task)

    def eventFilter(self, obj, event):
        """Arrow keys move through the popup while the line edit keeps focus.

        A filter rather than keyPressEvent: the edit has the focus, so the keys
        never reach this widget on their own, and the popup must not take focus
        or the edit would stop showing what was typed.
        """
        if obj is self.edit and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Escape and self.results.isVisible():
                self.results.hide()
                return True
            if key in (Qt.Key_Down, Qt.Key_Up) and self.results.isVisible():
                row = self.results.currentRow() + (1 if key == Qt.Key_Down
                                                   else -1)
                if 0 <= row < self.results.count():
                    self.results.setCurrentRow(row)
                return True
        return super().eventFilter(obj, event)
