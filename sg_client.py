import os

import shotgun_api3

import applog
import config

log = applog.get()


def _media_fields(info):
    """Stock Version fields worth filling in from an inspected media file.

    Kept separate from the required data because these are the fields most
    likely to have been renamed or removed on a given site.
    """
    if not info:
        return {}
    data = {}
    if getattr(info, "frames", None):
        data["frame_count"] = info.frames
        data["sg_first_frame"] = 1
        data["sg_last_frame"] = info.frames
        data["frame_range"] = f"1-{info.frames}"
    if getattr(info, "path", None):
        key = ("sg_path_to_movie" if getattr(info, "kind", "") == "movie"
               else "sg_path_to_frames")
        data[key] = info.path
    return data


class SGClient:
    def __init__(self):
        self._reset_caches()
        if os.environ.get("SGDESK_DEV") == "1":
            from sgdesk_dcc.devkit.mock_sg import MockShotgun
            self.sg = MockShotgun()
            return
        if not config.SG_SCRIPT_KEY:
            raise RuntimeError(
                "SG_SCRIPT_KEY is not set. Export it before starting ShotDeck "
                )
        self.sg = shotgun_api3.Shotgun(
            config.SG_SITE,
            script_name=config.SG_SCRIPT_NAME,
            api_key=config.SG_SCRIPT_KEY,
        )

    def _reset_caches(self):
        self._owner = None
        self._owner_value = None
        self._statuses = None            # Task statuses
        self._version_statuses = None    # Version statuses
        self._steps = None               # pipeline steps, aka departments
        self._version_field_cache = None

    @property
    def api_identity(self):
        """Which ShotGrid script the API calls authenticate as.

        Shown in the publish result so a supervisor can tell at a glance that a
        Version came through ShotDeck's daemon rather than a seat. Only the
        script *name* -- the key never leaves config.
        """
        return config.SG_SCRIPT_NAME

    # -- user / owner -----------------------------------------------------

    def resolve_owner(self, user_email):
        """Look up the user entity for this email address.

        In entity mode the entity itself is used in the task filter. In string
        mode (the default here) it is only used to obtain the value that
        Task.sg_assigned_to stores -- see config.TASK_OWNER_STRING_FIELD.
        """
        fields = [config.TASK_OWNER_MATCH_FIELD, "name"]
        if config.TASK_OWNER_STRING_FIELD not in fields:
            fields.append(config.TASK_OWNER_STRING_FIELD)
        self._owner = self.sg.find_one(
            config.TASK_OWNER_ENTITY,
            [[config.TASK_OWNER_MATCH_FIELD, "is", user_email]],
            fields,
        )
        self._owner_value = self._owner_string(user_email)
        return self._owner

    def _owner_string(self, user_email):
        """The value to compare Task.sg_assigned_to against, in string mode."""
        if config.TASK_OWNER_IS_ENTITY:
            return None
        if self._owner:
            value = self._owner.get(config.TASK_OWNER_STRING_FIELD)
            if value:
                return value
        # No matching entity, or the field is empty on it: the email address is
        # still worth trying, since that is what the tasks most likely store.
        return user_email

    @property
    def owner(self):
        return self._owner

    @property
    def owner_value(self):
        return self._owner_value

    # -- queries -----------------------------------------------------------

    def active_projects(self):
        return self.sg.find(
            "Project",
            [["sg_status", "is", "Active"], ["is_template", "is", False]],
            config.PROJECT_FIELDS,
            order=[{"field_name": "name", "direction": "asc"}],
        )

    def software_for_project(self, project):
        """Software active + either global (no project links) or linked to this project."""
        sws = self.sg.find(
            "Software",
            [["sg_status_list", "is", "act"]],
            config.SOFTWARE_FIELDS,
        )
        out = []
        for sw in sws:
            links = sw.get("projects") or []
            if links and not any(p["id"] == project["id"] for p in links):
                continue
            # Launchable means either a real path, or a rez request that
            # supplies the command itself.
            if sw.get("linux_path") or sw.get(config.SOFTWARE_REZ_FIELD):
                out.append(sw)
        return out

    # -- status ------------------------------------------------------------

    def task_statuses(self):
        """[(code, label), ...] straight from the site's status list.

        Read once and kept -- the schema does not change while ShotDeck is
        open, and this is called every time a context menu opens.
        """
        if self._statuses is not None:
            return self._statuses

        try:
            schema = self.sg.schema_field_read("Task", "sg_status_list")
            props = schema["sg_status_list"]["properties"]
            codes = props["valid_values"]["value"]
            # display_values is a code -> label map on most sites, but it is
            # not guaranteed to be there.
            labels = (props.get("display_values") or {}).get("value") or {}
        except Exception as e:
            log.warning("could not read the Task status list: %s", e)
            self._statuses = []
            return self._statuses

        self._statuses = [(c, labels.get(c, c)) for c in codes]
        return self._statuses

    def set_task_status(self, task_id, code):
        """Write a new status back to ShotGrid. Returns the updated task."""
        log.info("setting task %s status to %s", task_id, code)
        return self.sg.update("Task", task_id, {"sg_status_list": code})

    # -- publishing --------------------------------------------------------

    def versions_for_task(self, task_id):
        return self.sg.find(
            "Version",
            [[config.VERSION_TASK_FIELD, "is",
              {"type": "Task", "id": task_id}]],
            ["code", "created_at"],
            order=[{"field_name": "created_at", "direction": "desc"}],
        )

    # -- version browser ---------------------------------------------------

    def versions(self, entity=None, task_id=None, filters=None,
                 order=None, limit=0, page=1, fields=None):
        """Versions for a shot or a task, filtered on the server.

        `filters` is raw ShotGrid filter syntax so callers can push whatever
        the UI is asking for down to the API rather than fetching everything
        and sifting it here -- a busy shot has thousands of versions.
        """
        found = list(filters or [])
        if entity:
            found.append([config.VERSION_ENTITY_FIELD, "is",
                          {"type": entity["type"], "id": entity["id"]}])
        if task_id:
            found.append([config.VERSION_TASK_FIELD, "is",
                          {"type": "Task", "id": task_id}])
        return self.sg.find(
            "Version", found, fields or self._version_fields(),
            order=order or [{"field_name": "created_at",
                             "direction": "desc"}],
            limit=limit, page=page,
        )

    def _version_fields(self):
        """VERSION_FIELDS, plus any optional field this site turns out to have.

        Asking for a field the site does not have fails the whole query, so the
        optional list is probed once and then remembered.
        """
        if self._version_field_cache is not None:
            return self._version_field_cache

        fields = list(config.VERSION_FIELDS)
        for name in config.VERSION_OPTIONAL_FIELDS:
            try:
                if self.sg.schema_field_read("Version", name):
                    fields.append(name)
            except Exception as e:
                log.info("Version.%s not available on this site (%s)", name, e)
        self._version_field_cache = fields
        return fields

    def version_statuses(self):
        """[(code, label), ...] from the site's own Version status list."""
        if self._version_statuses is not None:
            return self._version_statuses
        try:
            schema = self.sg.schema_field_read("Version", "sg_status_list")
            props = schema["sg_status_list"]["properties"]
            codes = props["valid_values"]["value"]
            labels = (props.get("display_values") or {}).get("value") or {}
        except Exception as e:
            log.warning("could not read the Version status list: %s", e)
            self._version_statuses = []
            return self._version_statuses
        self._version_statuses = [(c, labels.get(c, c)) for c in codes]
        return self._version_statuses

    def steps(self):
        """Pipeline steps, which is what the browser calls Department."""
        if self._steps is not None:
            return self._steps
        try:
            self._steps = self.sg.find(
                "Step", [], ["code", "short_name", "entity_type"],
                order=[{"field_name": "code", "direction": "asc"}])
        except Exception as e:
            log.warning("could not read the Step list: %s", e)
            self._steps = []
        return self._steps

    # -- version writes ----------------------------------------------------

    def version_exists(self, project, code, task_id=None):
        """The Version with this name, if the site already has one.

        Checked against ShotGrid rather than the list the dialog happens to
        hold, so two artists publishing at the same moment cannot both believe
        v004 is free.
        """
        filters = [
            ["project", "is", {"type": "Project", "id": project["id"]}],
            ["code", "is", code],
        ]
        if task_id:
            filters.append([config.VERSION_TASK_FIELD, "is",
                            {"type": "Task", "id": task_id}])
        return self.sg.find_one("Version", filters, ["code", "created_at"])

    def create_version(self, project, task, name, description="",
                       media_info=None):
        """Create the Version row itself. No media yet.

        Authenticated as the script user (SG_SCRIPT_NAME), while `user` is set
        to the artist resolved at startup -- the API identity and the credited
        artist are two different things and must stay that way.
        """
        data = self._version_data(project, task, name, description)
        extra = _media_fields(media_info)
        if extra:
            try:
                return self.sg.create("Version", dict(data, **extra))
            except Exception as e:
                # Frame and resolution fields are stock but not universal, and
                # one missing field fails the whole create. The Version matters
                # more than the metadata.
                log.warning("create with media fields %s failed (%s); "
                            "creating without them", sorted(extra), e)
        return self.sg.create("Version", data)

    def _version_data(self, project, task, name, description):
        entity = (task or {}).get("entity")
        data = {
            "project": {"type": "Project", "id": project["id"]},
            "code": name,
            "description": description or "",
            config.VERSION_TASK_FIELD: {"type": "Task", "id": task["id"]},
        }
        if entity:
            data[config.VERSION_ENTITY_FIELD] = {
                "type": entity["type"], "id": entity["id"]}
        if config.VERSION_STATUS:
            data["sg_status_list"] = config.VERSION_STATUS
        if self._owner:
            data["user"] = {"type": self._owner["type"],
                            "id": self._owner["id"]}
        return data

    def upload_media(self, version_id, path):
        """Upload the media the ShotGrid player streams."""
        return self.sg.upload("Version", version_id, path,
                              field_name=config.VERSION_MEDIA_FIELD)

    def upload_version_thumbnail(self, version_id, path):
        return self.sg.upload_thumbnail("Version", version_id, path)

    def delete_version(self, version_id):
        """Retire a Version -- used to clean up after a cancelled publish."""
        log.info("deleting Version %s", version_id)
        return self.sg.delete("Version", version_id)

    def publish_version(self, project, task, name, path, description="",
                        on_progress=None, work_file=""):
        """Create a Version against a task and upload the media to it.

        Two round trips, and the upload is the slow one. `on_progress` is
        called with a short message before each stage so the dialog can say
        what it is waiting on.

        `work_file` is an optional DCC scene registered after the media. It is
        deliberately last: by the time it runs the Version exists and the media
        is uploaded, so a failure there is reported on the returned dict
        (`shotdeck_work_file_error`) rather than raised.
        """
        def say(msg):
            log.info(msg)
            if on_progress:
                on_progress(msg)

        say(f"Creating Version '{name}'…")
        version = self.sg.create(
            "Version", self._version_data(project, task, name, description))

        ext = os.path.splitext(path)[1].lower()
        is_movie = ext in config.MOVIE_EXTENSIONS

        say(f"Uploading {os.path.basename(path)}…")
        self.sg.upload("Version", version["id"], path,
                       field_name=config.VERSION_MEDIA_FIELD)

        # Movies get a thumbnail from transcoding; stills do not, so give the
        # Version something to show in list views.
        if not is_movie:
            say("Uploading thumbnail…")
            try:
                self.sg.upload_thumbnail("Version", version["id"], path)
            except Exception as e:
                # A format ShotGrid cannot make a thumbnail of (EXR, DPX) is
                # not a reason to call the publish failed.
                log.warning("thumbnail upload skipped: %s", e)

        if work_file:
            say(f"Registering {os.path.basename(work_file)}…")
            try:
                version["shotdeck_work_file"] = self.attach_work_file(
                    project, task, version, work_file)
            except Exception as e:
                log.warning("work file not registered: %s", e)
                version["shotdeck_work_file_error"] = str(e)

        say("Done")
        return version

    def attach_work_file(self, project, task, version, path):
        """Register the DCC scene that produced a Version.

        Returns a short sentence describing what was created, for the dialog to
        show. Raises if nothing could be registered at all -- the caller treats
        that as a warning, not a failed publish.
        """
        mode = (config.WORKFILE_MODE or "published_file").lower()
        name = os.path.basename(path)
        log.info("registering work file %s (mode=%s)", path, mode)

        if mode == "attachment":
            # field_name omitted: shotgun_api3 then links a plain Attachment to
            # the entity rather than writing a file field.
            self.sg.upload("Version", version["id"], path)
            self._record_work_path(version, path)
            return f"{name} uploaded to the Version"

        if mode == "path_only":
            self._record_work_path(version, path)
            return f"{name} recorded on the Version"

        published = self._create_published_file(project, task, version, path)
        self._record_work_path(version, path)
        return f"{name} published as PublishedFile {published['id']}"

    def _create_published_file(self, project, task, version, path):
        entity = (task or {}).get("entity")
        data = {
            "project": {"type": "Project", "id": project["id"]},
            "code": os.path.basename(path),
            config.PUBLISHED_FILE_TASK_FIELD: {"type": "Task",
                                               "id": task["id"]},
            config.PUBLISHED_FILE_VERSION_FIELD: {"type": "Version",
                                                  "id": version["id"]},
            config.PUBLISHED_FILE_PATH_FIELD: {"local_path": path},
        }
        if entity:
            data[config.PUBLISHED_FILE_ENTITY_FIELD] = {
                "type": entity["type"], "id": entity["id"]}

        file_type = self._published_file_type(path)
        if file_type:
            data["published_file_type"] = file_type

        try:
            return self.sg.create("PublishedFile", data)
        except Exception as e:
            # A local file link only resolves if a LocalStorage covers the
            # path. Without one ShotGrid rejects the whole create, and a
            # PublishedFile carrying the path as text still beats nothing.
            log.warning("PublishedFile create failed (%s); retrying without "
                        "the local path link", e)
            data.pop(config.PUBLISHED_FILE_PATH_FIELD, None)
            data["description"] = f"Work file: {path}"
            return self.sg.create("PublishedFile", data)

    def _published_file_type(self, path):
        """The site's PublishedFileType for this extension, if it has one."""
        name = config.PUBLISHED_FILE_TYPES.get(
            os.path.splitext(path)[1].lower())
        if not name:
            return None
        try:
            return self.sg.find_one("PublishedFileType",
                                    [["code", "is", name]], ["code"])
        except Exception as e:
            log.warning("could not look up PublishedFileType %r: %s", name, e)
            return None

    def _record_work_path(self, version, path):
        """Put the work file path somewhere visible on the Version itself."""
        field = config.VERSION_WORKFILE_FIELD
        if field:
            self.sg.update("Version", version["id"], {field: path})
            return
        existing = (version.get("description") or "").strip()
        note = f"Work file: {path}"
        self.sg.update("Version", version["id"],
                       {"description": f"{existing}\n{note}" if existing
                        else note})

    # -- queries -----------------------------------------------------------

    def my_tasks(self, project, statuses=None):
        if config.TASK_OWNER_IS_ENTITY:
            if not self._owner:
                return []
            owner_filter = [
                config.TASK_OWNER_FIELD, "is",
                {"type": self._owner["type"], "id": self._owner["id"]},
            ]
        else:
            if not self._owner_value:
                return []
            owner_filter = [
                config.TASK_OWNER_FIELD,
                config.TASK_OWNER_STRING_OP,
                self._owner_value,
            ]
        filters = [
            ["project", "is", {"type": "Project", "id": project["id"]}],
            owner_filter,
        ]
        if statuses:
            filters.append(["sg_status_list", "in", statuses])
        return self.sg.find(
            "Task", filters, config.TASK_FIELDS,
            order=[{"field_name": "due_date", "direction": "asc"}],
        )
