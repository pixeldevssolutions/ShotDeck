"""What needs the artist's attention, derived from ShotGrid.

Everything here comes from entities ShotGrid already keeps -- notes on versions
the artist published, replies to notes the artist wrote, and versions whose
status says a supervisor wants something changed. No event type is invented,
and nothing is stored in ShotGrid that was not already there.

The one thing kept locally is which items have been looked at, because
ShotGrid has no per-user read flag ShotDeck may write to. It is a small JSON
file of ids and a timestamp -- deliberately not a notification database.

Cost: four queries for the whole inbox, regardless of how many tasks, versions
or notes are involved. No Qt.
"""

import json
import os
import time

import applog
import config

log = applog.get()

NOTE = "NOTE"
NOTE_REPLY = "NOTE_REPLY"
VERSION_REJECTED = "VERSION_REJECTED"
REVISION_REQUESTED = "REVISION_REQUESTED"

LABELS = {
    NOTE: "New note",
    NOTE_REPLY: "Reply to your note",
    VERSION_REJECTED: "Version rejected",
    REVISION_REQUESTED: "Revision requested",
}

# Types that mean somebody is waiting on this artist, as opposed to types that
# are only worth knowing about.
ACTION_TYPES = {NOTE, VERSION_REJECTED, REVISION_REQUESTED}


class ReviewItem:
    """One thing worth looking at, normalised across the entities it came from."""

    def __init__(self, kind, created_at, project=None, entity=None, task=None,
                 version=None, note=None, author=None, text="", status=""):
        self.kind = kind
        self.created_at = created_at
        self.project = project or {}
        self.entity = entity or {}
        self.task = task or {}
        self.version = version or {}
        self.note = note or {}
        self.author = author or {}
        self.text = (text or "").strip()
        self.status = status

    @property
    def id(self):
        """Stable across refreshes, which is what read state is keyed on."""
        source = self.note or self.version
        return f"{self.kind}:{source.get('type', '?')}:{source.get('id', '?')}"

    @property
    def requires_action(self):
        return self.kind in ACTION_TYPES

    @property
    def label(self):
        return LABELS.get(self.kind, self.kind)

    @property
    def where(self):
        bits = [self.entity.get("name") or self.entity.get("code"),
                self.task.get("name") or self.task.get("content"),
                self.version.get("code")]
        return " / ".join(b for b in bits if b)

    def headline(self):
        who = self.author.get("name")
        if self.kind == NOTE:
            return f"{who} added a note" if who else "New note"
        if self.kind == NOTE_REPLY:
            return f"{who} replied to your note" if who else "Reply"
        if self.kind == VERSION_REJECTED:
            return "Version rejected"
        return "Revision requested"

    def __repr__(self):
        return f"<ReviewItem {self.kind} {self.where}>"


class ReadState:
    """Which items have been opened. Ids and a timestamp, nothing else."""

    def __init__(self, path=None):
        self.path = path or config.REVIEW_READ_STATE_PATH
        self.seen = {}
        self._load()

    def _load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
            self.seen = data.get("seen") or {}
        except (OSError, ValueError):
            self.seen = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump({"seen": self.seen}, f)
        except OSError as e:                          # pragma: no cover
            log.warning("could not save the review read state: %s", e)

    def is_read(self, item):
        return item.id in self.seen

    def mark_read(self, item):
        self.seen[item.id] = int(time.time())
        self.save()

    def mark_all_read(self, items):
        stamp = int(time.time())
        for item in items:
            self.seen[item.id] = stamp
        self.save()

    def prune(self, items):
        """Forget items that no longer come back, so the file stays small."""
        live = {i.id for i in items}
        self.seen = {k: v for k, v in self.seen.items() if k in live}
        self.save()


class ReviewService:
    def __init__(self, sg, read_state=None):
        self.sg = sg
        self.read_state = read_state or ReadState()

    # -- gathering ---------------------------------------------------------

    def needs_attention(self, project=None, days=None):
        """[ReviewItem, ...] newest first.

        Four queries whatever the size of the show:

          1. the artist's own versions in the window
          2. notes on those versions
          3. notes the artist wrote (to find replies to them)
          4. replies to those notes

        Versions whose status asks for a revision come out of query 1, so they
        cost nothing extra.
        """
        owner = getattr(self.sg, "owner", None)
        if not owner:
            log.info("no ShotGrid user resolved; the review inbox is empty")
            return []

        days = days or config.REVIEW_WINDOW_DAYS
        mine = self.sg.versions_by_user(owner, project=project, days=days)
        items = list(self._status_items(mine))
        items.extend(self._note_items(mine, owner))
        items.extend(self._reply_items(owner, project, days))

        items.sort(key=lambda i: i.created_at or 0, reverse=True)
        return items

    def _status_items(self, versions):
        """Versions a supervisor pushed back, straight off the status field."""
        for version in versions:
            status = (version.get("sg_status_list") or "").lower()
            kind = config.REVIEW_STATUS_TYPES.get(status)
            if not kind:
                continue
            yield ReviewItem(
                kind,
                version.get("updated_at") or version.get("created_at"),
                project=version.get("project"),
                entity=version.get("entity"),
                task=version.get("sg_task"),
                version=version,
                status=status,
                text=version.get("description") or "")

    def _note_items(self, versions, owner):
        """Notes somebody else left on the artist's own versions."""
        by_id = {v["id"]: v for v in versions}
        if not by_id:
            return []
        notes = self.sg.notes_for_versions(list(by_id)) or []
        authors = self.sg.users([(n.get("user") or {}).get("id")
                                 for n in notes])

        items = []
        for note in notes:
            author_id = (note.get("user") or {}).get("id")
            if author_id == owner.get("id"):
                continue                # your own note is not news to you
            version = _linked_version(note, by_id)
            if not version:
                continue
            items.append(ReviewItem(
                NOTE, note.get("created_at"),
                project=note.get("project"),
                entity=version.get("entity"),
                task=version.get("sg_task"),
                version=version, note=note,
                author=authors.get(author_id) or note.get("user"),
                text=note.get("content") or note.get("subject") or ""))
        return items

    def _reply_items(self, owner, project, days):
        """Replies to notes the artist wrote, wherever those notes live."""
        my_notes = self.sg.notes_by_user(owner, project=project, days=days)
        if not my_notes:
            return []
        by_id = {n["id"]: n for n in my_notes}
        replies = self.sg.replies_for_notes(list(by_id)) or []
        authors = self.sg.users([(r.get("user") or {}).get("id")
                                 for r in replies])

        items = []
        for reply in replies:
            author_id = (reply.get("user") or {}).get("id")
            if author_id == owner.get("id"):
                continue
            note = by_id.get((reply.get("entity") or {}).get("id"))
            if not note:
                continue
            version = _note_version(note)
            items.append(ReviewItem(
                NOTE_REPLY, reply.get("created_at"),
                project=note.get("project"),
                entity=_note_entity(note),
                task=(note.get("tasks") or [None])[0],
                version=version, note=note,
                author=authors.get(author_id) or reply.get("user"),
                text=reply.get("content") or ""))
        return items

    # -- read state --------------------------------------------------------

    def unread(self, items):
        return [i for i in items if not self.read_state.is_read(i)]

    def mark_read(self, item):
        self.read_state.mark_read(item)

    def attention_by_task(self, items):
        """{task id: why}, for the dot on the task row.

        Unread items only, and the reason travels with it -- a dot that cannot
        explain itself is noise.
        """
        reasons = {}
        for item in items:
            task_id = (item.task or {}).get("id")
            if not task_id or self.read_state.is_read(item):
                continue
            when = _ago(item.created_at)
            reason = f"{item.headline()} on {item.version.get('code') or ''}"
            reasons.setdefault(task_id, f"{reason}{when}")
        return reasons


# -- helpers ----------------------------------------------------------------

def _linked_version(note, by_id):
    for link in note.get("note_links") or []:
        if link.get("type") == "Version" and link.get("id") in by_id:
            return by_id[link["id"]]
    return None


def _note_version(note):
    for link in note.get("note_links") or []:
        if link.get("type") == "Version":
            return link
    return {}


def _note_entity(note):
    for link in note.get("note_links") or []:
        if link.get("type") not in ("Version", "Task"):
            return link
    return {}


def _ago(when):
    if not when or isinstance(when, str):
        return ""
    import datetime
    now = datetime.datetime.now(when.tzinfo) if when.tzinfo else \
        datetime.datetime.now()
    seconds = (now - when).total_seconds()
    if seconds < 3600:
        return f", {int(seconds // 60)} min ago"
    if seconds < 86400:
        return f", {int(seconds // 3600)}h ago"
    days = int(seconds // 86400)
    return ", yesterday" if days == 1 else f", {days} days ago"
