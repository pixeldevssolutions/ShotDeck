import os

import shotgun_api3
import config


class SGClient:
    def __init__(self):
        if os.environ.get("SGDESK_DEV") == "1":
            from sgdesk_dcc.devkit.mock_sg import MockShotgun
            self.sg = MockShotgun()
            self._owner = None
            self._owner_value = None
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
