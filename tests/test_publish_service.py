"""The publish itself: context, naming, permissions, cancellation, cleanup."""

import os
import tempfile

import config
import fakes
import publish_service as ps

TMP = tempfile.mkdtemp(prefix="flow-tests-")


def _file(name, size=2048):
    path = os.path.join(TMP, name)
    with open(path, "wb") as f:
        f.write(b"\x00" * size)
    return path


MOV = _file("SH010_comp_v004.mov")
JPG = _file("SH010_comp_v004.jpg")
TXT = _file("notes.txt")
EMPTY = _file("empty.mov", 0)


def service(sg=None):
    return ps.PublishService(fakes.client(sg))


def request(name="SH010_Comp_v004", media=MOV, **kw):
    # These fixtures live in the OS temp directory, which the path policy
    # warns about — correctly. The warning is accepted here so these tests
    # exercise the publish rather than the path policy; test_path_validator
    # and test_preflight cover the policy itself.
    kw.setdefault("accepted_warnings", True)
    return ps.PublishRequest(fakes.PROJECT, fakes.TASK, name, media, **kw)


# -- context ---------------------------------------------------------------

def test_valid_context_passes():
    assert service().validate_context(fakes.PROJECT, fakes.TASK) is True


def test_missing_task_is_refused():
    try:
        service().validate_context(fakes.PROJECT, None)
    except ps.ContextError as e:
        assert "No task selected" in str(e)
    else:
        raise AssertionError("a missing task should not be publishable")


def test_task_without_entity_is_refused():
    try:
        service().validate_context(fakes.PROJECT, fakes.TASK_NO_ENTITY)
    except ps.ContextError as e:
        assert "not linked" in str(e)
    else:
        raise AssertionError("a task with no shot should not be publishable")


# -- media -----------------------------------------------------------------

def test_movie_and_image_are_accepted():
    svc = service()
    assert svc.inspect_media(MOV).kind == "movie"
    assert svc.inspect_media(JPG).kind == "image"


def test_unsupported_format_is_refused():
    try:
        service().inspect_media(TXT)
    except ps.MediaError as e:
        assert ".txt" in str(e)
    else:
        raise AssertionError(".txt should not be publishable")


def test_missing_file_is_refused():
    try:
        service().inspect_media(os.path.join(TMP, "nope.mov"))
    except ps.MediaError as e:
        assert "no longer exists" in str(e)
    else:
        raise AssertionError("a missing file should not be publishable")


def test_empty_file_is_refused():
    try:
        service().inspect_media(EMPTY)
    except ps.MediaError as e:
        assert "empty" in str(e)
    else:
        raise AssertionError("an empty file should not be publishable")


def test_no_file_chosen_is_refused():
    try:
        service().inspect_media("")
    except ps.MediaError:
        pass
    else:
        raise AssertionError("publishing nothing should be refused")


# -- version naming --------------------------------------------------------

def test_first_version_is_v001():
    assert ps.next_version_name(fakes.TASK, []) == "SH010_Comp_v001"


def test_name_continues_from_the_highest():
    existing = [{"code": "SH010_Comp_v001"}, {"code": "SH010_Comp_v003"}]
    assert ps.next_version_name(fakes.TASK, existing) == "SH010_Comp_v004"


def test_numbering_ignores_unnumbered_versions():
    existing = [{"code": "SH010_Comp_wip"}, {"code": "SH010_Comp_v002"}]
    assert ps.next_version_name(fakes.TASK, existing) == "SH010_Comp_v003"


def test_suggestion_reads_existing_versions_from_shotgrid():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v007")
    assert service(sg).suggest_version_name(fakes.TASK) == "SH010_Comp_v008"


def test_duplicate_name_is_refused():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v004")
    try:
        service(sg).check_name_available(fakes.PROJECT, fakes.TASK,
                                         "SH010_Comp_v004")
    except ps.DuplicateVersionError as e:
        assert "already exists" in str(e)
    else:
        raise AssertionError("an existing version name must be refused")


def test_free_name_is_allowed():
    sg = fakes.FakeShotgun()
    sg.add_version("SH010_Comp_v003")
    assert service(sg).check_name_available(
        fakes.PROJECT, fakes.TASK, "SH010_Comp_v004") is None


def test_publish_rechecks_the_name_against_the_server():
    """The dialog's list can be stale; the server's answer is the one that
    counts, so a version created by someone else in the meantime still wins."""
    sg = fakes.FakeShotgun()
    svc = service(sg)
    sg.add_version("SH010_Comp_v004")          # another artist got there first
    try:
        svc.publish(request())
    except ps.DuplicateVersionError:
        pass
    else:
        raise AssertionError("the race should have been caught")
    assert not sg.uploads, "nothing should have been uploaded"


# -- publishing ------------------------------------------------------------

def test_publish_creates_uploads_and_credits_the_artist():
    sg = fakes.FakeShotgun()
    stages = []
    result = service(sg).publish(request(), on_stage=stages.append)

    version = result.version
    assert version["code"] == "SH010_Comp_v004"
    assert version["user"]["id"] == fakes.ARTIST["id"], \
        "the Version must credit the artist, not the script user"
    assert version[config.VERSION_TASK_FIELD]["id"] == fakes.TASK["id"]
    assert version[config.VERSION_ENTITY_FIELD]["id"] == fakes.SHOT["id"]
    assert sg.uploads and sg.uploads[0][2] == config.VERSION_MEDIA_FIELD
    assert any("Uploading" in s for s in stages)
    assert result.url.endswith(f"/detail/Version/{version['id']}")


def test_still_publish_also_uploads_a_thumbnail():
    sg = fakes.FakeShotgun()
    service(sg).publish(request(media=JPG))
    assert any(c[0] == "upload_thumbnail" for c in sg.calls)


def test_movie_publish_does_not_upload_a_thumbnail():
    sg = fakes.FakeShotgun()
    service(sg).publish(request())
    assert not any(c[0] == "upload_thumbnail" for c in sg.calls)


def test_permission_failure_is_readable():
    sg = fakes.FakeShotgun()
    sg.fail_create = RuntimeError(
        "API create() CRUD ERROR #3: Create on Version is not permitted")
    try:
        service(sg).publish(request())
    except ps.PermissionDenied as e:
        assert "permission" in str(e).lower()
        assert "not permitted" in e.detail
    else:
        raise AssertionError("a permission error needs its own message")


def test_connection_failure_is_readable():
    sg = fakes.FakeShotgun()
    sg.fail_create = RuntimeError("Max retries exceeded: connection refused")
    try:
        service(sg).publish(request())
    except ps.ConnectionFailed as e:
        assert "could not be reached" in str(e)
    else:
        raise AssertionError("a network error needs its own message")


def test_authentication_failure_is_readable():
    sg = fakes.FakeShotgun()
    sg.fail_create = RuntimeError("Authentication failed: invalid script name")
    try:
        service(sg).publish(request())
    except ps.AuthFailed:
        pass
    else:
        raise AssertionError("an auth error needs its own message")


def test_failed_upload_removes_the_empty_version():
    sg = fakes.FakeShotgun()
    sg.fail_upload = RuntimeError("Upload interrupted")
    try:
        service(sg).publish(request())
    except ps.PublishError:
        pass
    else:
        raise AssertionError("a failed upload is a failed publish")
    assert sg.deleted, "a Version with no media must not be left behind"


def test_cancel_before_the_create_touches_nothing():
    sg = fakes.FakeShotgun()
    try:
        service(sg).publish(request(), cancelled=lambda: True)
    except ps.PublishCancelled:
        pass
    else:
        raise AssertionError("cancelling should raise PublishCancelled")
    assert not any(c[0] == "create" for c in sg.calls)


def test_cancel_after_the_create_cleans_up():
    sg = fakes.FakeShotgun()
    calls = {"n": 0}

    def cancelled():
        # Not cancelled at the first checkpoint, cancelled at the next.
        calls["n"] += 1
        return calls["n"] > 1

    try:
        service(sg).publish(request(), cancelled=cancelled)
    except ps.PublishCancelled as e:
        assert "removed" in str(e)
    else:
        raise AssertionError("cancelling should raise PublishCancelled")
    assert sg.deleted, "the half-made Version should have been removed"


def test_cleanup_failure_does_not_mask_the_real_error():
    sg = fakes.FakeShotgun()
    sg.fail_upload = RuntimeError("Upload interrupted")
    sg.fail_delete = RuntimeError("Delete on Version is not permitted")
    try:
        service(sg).publish(request())
    except ps.PublishError as e:
        assert "Upload interrupted" in (e.detail or "")
    else:
        raise AssertionError("the upload failure is what the artist needs")


def test_work_file_failure_does_not_fail_the_publish():
    sg = fakes.FakeShotgun()
    nk = _file("SH010_comp_v004.nk", 12)
    old_mode = config.WORKFILE_MODE
    config.WORKFILE_MODE = "published_file"
    original = sg.create

    def create(entity_type, data):
        if entity_type == "PublishedFile":
            raise RuntimeError("Create on PublishedFile is not permitted")
        return original(entity_type, data)

    sg.create = create
    try:
        result = service(sg).publish(request(work_file=nk))
    finally:
        config.WORKFILE_MODE = old_mode
    assert result.version["id"], "the Version must survive a work file problem"
    assert "not permitted" in result.work_file_error


def test_audit_log_never_contains_a_key():
    """The audit helper scrubs anything that smells like a credential."""
    assert ps._scrub("api_key", "abc123") == "***"
    assert ps._scrub("script_secret", "abc") == "***"
    assert ps._scrub("version_name", "SH010_Comp_v004") == "SH010_Comp_v004"
