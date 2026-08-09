"""Filter building for the Version browser."""

import version_query as vq


def test_no_filters_by_default():
    assert vq.build_filters() == []


def test_department_filters_through_the_task():
    filters = vq.build_filters(step={"type": "Step", "id": 9})
    assert filters == [["sg_task.Task.step", "is",
                        {"type": "Step", "id": 9}]]


def test_user_and_status_filter():
    filters = vq.build_filters(user={"type": "HumanUser", "id": 42},
                               status="apr")
    assert ["user", "is", {"type": "HumanUser", "id": 42}] in filters
    assert ["sg_status_list", "is", "apr"] in filters


def test_date_ranges():
    assert vq.build_filters(date_key="today") == \
        [["created_at", "in_calendar_day", 0]]
    assert vq.build_filters(date_key="yesterday") == \
        [["created_at", "in_calendar_day", -1]]
    assert vq.build_filters(date_key="7") == \
        [["created_at", "in_last", [7, "DAY"]]]
    assert vq.build_filters(date_key="30") == \
        [["created_at", "in_last", [30, "DAY"]]]
    assert vq.build_filters(date_key="all") == []


def test_custom_range_needs_both_ends():
    assert vq.build_filters(date_key="custom") == []
    assert vq.build_filters(date_key="custom",
                            date_range=("2026-08-01", "2026-08-09")) == \
        [["created_at", "between", ["2026-08-01", "2026-08-09"]]]


def test_search_widens_rather_than_narrows():
    """One "any" group: typing an artist name must not exclude every version
    whose *code* does not contain it."""
    filters = vq.build_filters(search="jitesh")
    assert len(filters) == 1
    group = filters[0]
    assert group["filter_operator"] == "any"
    fields = [f[0] for f in group["filters"]]
    assert "code" in fields and "description" in fields
    assert "user.HumanUser.name" in fields


def test_search_is_trimmed_and_optional():
    assert vq.build_filters(search="   ") == []


def test_filters_combine():
    filters = vq.build_filters(search="comp", status="rev",
                               step={"type": "Step", "id": 9})
    assert len(filters) == 3


def test_sort_orders_are_all_valid():
    for key, label, order in vq.SORT_ORDERS:
        assert label and order
        assert all("field_name" in o and "direction" in o for o in order)
    assert vq.order_for("created_asc")[0]["direction"] == "asc"
    # An unknown key falls back to the default rather than breaking the query.
    assert vq.order_for("nonsense") == vq.SORT_ORDERS[0][2]


def test_default_sort_is_newest_first():
    order = vq.order_for(vq.DEFAULT_SORT)
    assert order[0] == {"field_name": "created_at", "direction": "desc"}


def test_options_come_from_the_data_on_screen():
    versions = [
        {"user": {"type": "HumanUser", "id": 42, "name": "Jitesh"},
         "sg_task.Task.step": {"type": "Step", "id": 9, "name": "Comp"},
         "sg_status_list": "rev"},
        {"user": {"type": "HumanUser", "id": 43, "name": "Rahul"},
         "sg_task.Task.step": {"type": "Step", "id": 9, "name": "Comp"},
         "sg_status_list": "wip"},
        {"user": {"type": "HumanUser", "id": 42, "name": "Jitesh"},
         "sg_status_list": "wip"},
    ]
    options = vq.options_from(versions)
    assert [u["name"] for u in options["users"]] == ["Jitesh", "Rahul"]
    assert len(options["steps"]) == 1
    assert options["statuses"] == ["rev", "wip"]


def test_options_survive_missing_fields():
    assert vq.options_from([{}, {"user": None}])["users"] == []
    assert vq.options_from(None)["statuses"] == []
