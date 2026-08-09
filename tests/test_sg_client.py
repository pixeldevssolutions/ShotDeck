"""The ShotGrid layer: identity, queries, version writes, work files."""

import config
import fakes
import media_inspector


def test_api_identity_is_the_script_not_the_key():
    client = fakes.client()
    assert client.api_identity == config.SG_SCRIPT_NAME
    assert config.SG_SCRIPT_KEY not in str(client.api_identity)


def test_created_version_credits_the_artist():
    """Authentication is the script user; attribution is the artist."""
    sg = fakes.FakeShotgun()
    version = fakes.client(sg).create_version(
        fakes.PROJECT, fakes.TASK, "SH010_Comp_v001")
    assert version["user"] == {"type": "HumanUser", "id": fakes.ARTIST["id"]}


def test_media_fields_are_dropped_if_the_site_rejects_them():
    """One missing stock field must not cost the whole Version."""
    sg = fakes.FakeShotgun()
    info = media_inspector.MediaInfo(__file__)
    info.frames, info.kind = 120, "movie"

    original = sg.create
    calls = {"n": 0}

    def create(entity_type, data):
        calls["n"] += 1
        if "frame_count" in data:
            raise RuntimeError("Version.frame_count does not exist")
        return original(entity_type, data)

    sg.create = create
    version = fakes.client(sg).create_version(
        fakes.PROJECT, fakes.TASK, "SH010_Comp_v001", media_info=info)
    assert calls["n"] == 2
    assert version["code"] == "SH010_Comp_v001"


def test_version_exists_is_scoped_to_the_task():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v001")
    client = fakes.client(sg)
    assert client.version_exists(fakes.PROJECT, "SH010_Comp_v001",
                                 fakes.TASK["id"])
    assert not client.version_exists(fakes.PROJECT, "SH010_Comp_v999",
                                     fakes.TASK["id"])


def test_versions_query_is_paged_and_ordered():
    sg = fakes.FakeShotgun()
    for i in range(1, 6):
        sg.add_version(f"SH010_Comp_v00{i}")
    client = fakes.client(sg)

    page1 = client.versions(entity=fakes.SHOT, limit=2, page=1)
    page2 = client.versions(entity=fakes.SHOT, limit=2, page=2)
    assert [v["code"] for v in page1] == ["SH010_Comp_v005",
                                          "SH010_Comp_v004"]
    assert [v["code"] for v in page2] == ["SH010_Comp_v003",
                                          "SH010_Comp_v002"]


def test_versions_query_pushes_filters_to_the_server():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v001", sg_status_list="apr")
    sg.add_version("SH010_Comp_v002", sg_status_list="wip")
    rows = fakes.client(sg).versions(
        entity=fakes.SHOT, filters=[["sg_status_list", "is", "apr"]])
    assert [v["code"] for v in rows] == ["SH010_Comp_v001"]
    # The filter went into the find() call rather than being applied here.
    find = [c for c in sg.calls if c[0] == "find"][-1]
    assert ["sg_status_list", "is", "apr"] in find[2]


def test_version_statuses_come_from_the_schema_and_are_cached():
    sg = fakes.FakeShotgun()
    client = fakes.client(sg)
    assert client.version_statuses() == [
        ("wip", "Work In Progress"), ("rev", "Pending Review"),
        ("apr", "Approved")]
    client.version_statuses()
    assert len([c for c in sg.calls if c[0] == "schema_field_read"]) == 1


def test_steps_are_cached_too():
    sg = fakes.FakeShotgun()
    client = fakes.client(sg)
    assert len(client.steps()) == 3
    client.steps()
    assert len([c for c in sg.calls if c[0] == "find" and c[1] == "Step"]) == 1


def test_status_list_failure_degrades_to_empty():
    sg = fakes.FakeShotgun()

    def boom(*a, **k):
        raise RuntimeError("schema_field_read is not permitted")

    sg.schema_field_read = boom
    assert fakes.client(sg).version_statuses() == []


def test_work_file_published_file_links_version_task_and_entity():
    sg = fakes.FakeShotgun()
    old = config.WORKFILE_MODE
    config.WORKFILE_MODE = "published_file"
    try:
        note = fakes.client(sg).attach_work_file(
            fakes.PROJECT, fakes.TASK, {"id": 9001},
            "/jobs/UAT6/nuke/comp/SH010_comp_v004.nk")
    finally:
        config.WORKFILE_MODE = old

    published = sg.published_files[0]
    assert published[config.PUBLISHED_FILE_VERSION_FIELD]["id"] == 9001
    assert published[config.PUBLISHED_FILE_TASK_FIELD]["id"] == fakes.TASK["id"]
    assert published[config.PUBLISHED_FILE_ENTITY_FIELD]["id"] == \
        fakes.SHOT["id"]
    assert "PublishedFile" in note


def test_work_file_attachment_mode_uploads_instead():
    sg = fakes.FakeShotgun()
    old = config.WORKFILE_MODE
    config.WORKFILE_MODE = "attachment"
    try:
        fakes.client(sg).attach_work_file(
            fakes.PROJECT, fakes.TASK, {"id": 9001}, "/jobs/x/scene.ma")
    finally:
        config.WORKFILE_MODE = old
    assert sg.uploads[0][2] is None       # a plain Attachment, not a field
    assert not sg.published_files


def test_delete_version_removes_it():
    sg = fakes.FakeShotgun()
    version = sg.add_version("SH010_Comp_v001")
    fakes.client(sg).delete_version(version["id"])
    assert sg.deleted == [("Version", version["id"])]
