import os

import shotgun_api3

import applog
import config

log = applog.get()


class SGClient:
    def __init__(self):
        if os.environ.get("SGDESK_DEV") == "1":
            from sgdesk_dcc.devkit.mock_sg import MockShotgun
            self.sg = MockShotgun()
            self._owner = None
            self._owner_value = None
            self._statuses = None
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
        self._owner = None
        self._owner_value = None
        self._statuses = None

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

    def publish_version(self, project, task, name, path, description="",
                        on_progress=None):
        """Create a Version against a task and upload the media to it.

        Two round trips, and the upload is the slow one. `on_progress` is
        called with a short message before each stage so the dialog can say
        what it is waiting on.
        """
        def say(msg):
            log.info(msg)
            if on_progress:
                on_progress(msg)

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

        say(f"Creating Version '{name}'…")
        version = self.sg.create("Version", data)

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

        say("Done")
        return version

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
