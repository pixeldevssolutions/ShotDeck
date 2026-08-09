"""Turning what the Version browser is showing into ShotGrid filters.

Kept apart from the widgets so the filtering can be tested without a screen,
and so every filter is pushed to the server: a busy shot has thousands of
versions and sifting them in the client is how a browser becomes unusable in
month three of a show.
"""

# Date filters, in ShotGrid's own relative-date syntax. "in_calendar_day" takes
# an offset in days: 0 is today, -1 yesterday.
DATE_RANGES = [
    ("all", "All"),
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("7", "Last 7 Days"),
    ("30", "Last 30 Days"),
    ("custom", "Custom Range"),
]

SORT_ORDERS = [
    ("created_desc", "Date — Newest First",
     [{"field_name": "created_at", "direction": "desc"}]),
    ("created_asc", "Date — Oldest First",
     [{"field_name": "created_at", "direction": "asc"}]),
    ("code_desc", "Version Number",
     [{"field_name": "code", "direction": "desc"}]),
    ("code_asc", "Version Name",
     [{"field_name": "code", "direction": "asc"}]),
    ("user", "Artist",
     [{"field_name": "user", "direction": "asc"},
      {"field_name": "created_at", "direction": "desc"}]),
    ("step", "Department",
     [{"field_name": "sg_task.Task.step", "direction": "asc"},
      {"field_name": "created_at", "direction": "desc"}]),
    ("status", "Status",
     [{"field_name": "sg_status_list", "direction": "asc"},
      {"field_name": "created_at", "direction": "desc"}]),
]

DEFAULT_SORT = "created_desc"

# Fields a typed search looks in. Deep fields mean an artist can type a shot
# name or an artist name and get what they expect.
SEARCH_FIELDS = [
    "code",
    "description",
    "user.HumanUser.name",
    "sg_task.Task.content",
    "entity.Shot.code",
    "entity.Asset.code",
]


def order_for(key):
    for k, _label, order in SORT_ORDERS:
        if k == key:
            return order
    return SORT_ORDERS[0][2]


def build_filters(search="", step=None, user=None, status="",
                  date_key="all", date_range=None):
    """ShotGrid filters for the browser's current state.

    `step` and `user` are entity dicts (or None for All), `status` a short
    code, `date_range` a (start, end) pair of dates used only when `date_key`
    is "custom".
    """
    filters = []

    if step:
        filters.append(["sg_task.Task.step", "is",
                        {"type": "Step", "id": step["id"]}])
    if user:
        filters.append(["user", "is",
                        {"type": user.get("type", "HumanUser"),
                         "id": user["id"]}])
    if status:
        filters.append(["sg_status_list", "is", status])

    date_filter = _date_filter(date_key, date_range)
    if date_filter:
        filters.append(date_filter)

    text = (search or "").strip()
    if text:
        # One "any" group rather than several filters, so the terms widen the
        # search instead of narrowing it to nothing.
        filters.append({
            "filter_operator": "any",
            "filters": [[f, "contains", text] for f in SEARCH_FIELDS],
        })
    return filters


def _date_filter(key, date_range):
    if key in ("all", "", None):
        return None
    if key == "today":
        return ["created_at", "in_calendar_day", 0]
    if key == "yesterday":
        return ["created_at", "in_calendar_day", -1]
    if key in ("7", "30"):
        return ["created_at", "in_last", [int(key), "DAY"]]
    if key == "custom" and date_range:
        start, end = date_range
        return ["created_at", "between", [start, end]]
    return None


def options_from(versions):
    """Filter choices actually present in the versions we have.

    The step list comes from ShotGrid's own Step entities, but the artist list
    is built from the data on screen: fetching every HumanUser on the site to
    populate a dropdown for one shot is exactly the kind of query that makes a
    tool feel slow.
    """
    users, steps, statuses = {}, {}, set()
    for v in versions or []:
        user = v.get("user") or v.get("created_by")
        if user and user.get("id") is not None:
            users[user["id"]] = user
        step = v.get("sg_task.Task.step")
        if step and step.get("id") is not None:
            steps[step["id"]] = step
        if v.get("sg_status_list"):
            statuses.add(v["sg_status_list"])
    return {
        "users": sorted(users.values(), key=lambda u: (u.get("name") or "")),
        "steps": sorted(steps.values(), key=lambda s: (s.get("name") or
                                                       s.get("code") or "")),
        "statuses": sorted(statuses),
    }
