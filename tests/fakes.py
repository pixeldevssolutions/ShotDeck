"""Stand-ins for ShotGrid and for a project's data.

The fake speaks the same subset of the shotgun_api3 API that SGClient uses, so
the tests exercise the real client and the real service rather than a mock of
them.
"""

import datetime


PROJECT = {"id": 1213, "name": "UAT6", "tank_name": "UAT6"}

SHOT = {"type": "Shot", "id": 2430, "name": "SH010"}

TASK = {
    "id": 7631,
    "content": "Compositing",
    "sg_status_list": "ip",
    "step": {"type": "Step", "id": 9, "name": "Comp"},
    "entity": SHOT,
    "project": PROJECT,
}

TASK_NO_ENTITY = dict(TASK, id=7632, entity=None)

ARTIST = {"type": "HumanUser", "id": 42, "name": "Jitesh",
          "email": "jitesh@5and8.ai"}


class FakeShotgun:
    """Enough of shotgun_api3.Shotgun to publish and to browse."""

    def __init__(self, versions=None):
        self.calls = []
        self.versions = list(versions or [])
        self.published_files = []
        self.uploads = []
        self.deleted = []
        self._next_id = 9000
        # Set any of these to an exception to make that operation fail.
        self.fail_create = None
        self.fail_upload = None
        self.fail_delete = None
        self.fail_find = None

    # -- helpers used by the tests ----------------------------------------

    def add_version(self, code, **fields):
        # Each one lands a minute after the last, so "newest first" has
        # something real to sort on.
        seq = len(self.versions)
        version = {
            "type": "Version", "id": self._new_id(), "code": code,
            "created_at": datetime.datetime(2026, 8, 8, 14, 21)
            + datetime.timedelta(minutes=seq),
            "sg_status_list": "rev", "user": ARTIST,
            "project": PROJECT,
            "sg_task": {"type": "Task", "id": TASK["id"]},
            "entity": SHOT,
        }
        version.update(fields)
        self.versions.append(version)
        return version

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    # -- the API ------------------------------------------------------------

    def find(self, entity_type, filters, fields=None, order=None,
             limit=0, page=1, **kwargs):
        self.calls.append(("find", entity_type, filters, order, limit, page))
        if self.fail_find:
            raise self.fail_find
        if entity_type == "Version":
            rows = [v for v in self.versions if _matches(v, filters)]
            if order:
                key = order[0]["field_name"]
                rows.sort(key=lambda v: str(v.get(key) or ""),
                          reverse=order[0]["direction"] == "desc")
            if limit:
                start = (page - 1) * limit
                rows = rows[start:start + limit]
            return rows
        if entity_type == "Step":
            return [{"type": "Step", "id": 9, "code": "Comp",
                     "entity_type": "Shot"},
                    {"type": "Step", "id": 10, "code": "Lighting",
                     "entity_type": "Shot"},
                    {"type": "Step", "id": 11, "code": "Modeling",
                     "entity_type": "Asset"}]
        return []

    def find_one(self, entity_type, filters, fields=None, **kwargs):
        rows = self.find(entity_type, filters, fields)
        return rows[0] if rows else None

    def create(self, entity_type, data):
        self.calls.append(("create", entity_type, data))
        if self.fail_create:
            raise self.fail_create
        row = dict(data)
        row.update({"type": entity_type, "id": self._new_id()})
        if entity_type == "Version":
            row.setdefault("created_at", datetime.datetime.now())
            self.versions.append(row)
        if entity_type == "PublishedFile":
            self.published_files.append(row)
        return row

    def update(self, entity_type, entity_id, data):
        self.calls.append(("update", entity_type, entity_id, data))
        for v in self.versions:
            if v["id"] == entity_id:
                v.update(data)
        return {"type": entity_type, "id": entity_id, **data}

    def delete(self, entity_type, entity_id):
        self.calls.append(("delete", entity_type, entity_id))
        if self.fail_delete:
            raise self.fail_delete
        self.deleted.append((entity_type, entity_id))
        self.versions = [v for v in self.versions if v["id"] != entity_id]
        return True

    def upload(self, entity_type, entity_id, path, field_name=None, **kwargs):
        self.calls.append(("upload", entity_type, entity_id, path, field_name))
        if self.fail_upload:
            raise self.fail_upload
        self.uploads.append((entity_id, path, field_name))
        return 555

    def upload_thumbnail(self, entity_type, entity_id, path):
        self.calls.append(("upload_thumbnail", entity_type, entity_id, path))
        return 556

    def schema_field_read(self, entity_type, field):
        self.calls.append(("schema_field_read", entity_type, field))
        return {field: {"properties": {
            "valid_values": {"value": ["wip", "rev", "apr"]},
            "display_values": {"value": {"wip": "Work In Progress",
                                         "rev": "Pending Review",
                                         "apr": "Approved"}},
        }}}


def _matches(version, filters):
    """Only the filter forms the client actually sends."""
    for f in filters or []:
        if isinstance(f, dict):                     # an "any" search group
            if not any(_matches(version, [sub]) for sub in f["filters"]):
                return False
            continue
        field, op, value = f[0], f[1], f[2]
        actual = _deep_get(version, field)
        if op == "is":
            if isinstance(value, dict):
                if not actual or actual.get("id") != value["id"]:
                    return False
            elif actual != value:
                return False
        elif op == "contains":
            haystack = actual if isinstance(actual, str) else \
                (actual or {}).get("name", "") if isinstance(actual, dict) \
                else ""
            if str(value).lower() not in haystack.lower():
                return False
        elif op in ("in_last", "in_calendar_day", "between"):
            continue          # dates are the server's business, not the fake's
    return True


def _deep_get(version, field):
    if field in version:
        return version[field]
    # "user.HumanUser.name" style
    parts = field.split(".")
    value = version.get(parts[0])
    if isinstance(value, dict) and len(parts) == 3:
        return value.get(parts[2])
    return None


def client(sg=None):
    """An SGClient wired to the fake, without touching the network."""
    import sg_client
    c = sg_client.SGClient.__new__(sg_client.SGClient)
    c._reset_caches()
    c.sg = sg or FakeShotgun()
    c._owner = ARTIST
    c._owner_value = ARTIST["email"]
    return c
