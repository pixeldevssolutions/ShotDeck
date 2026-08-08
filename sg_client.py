import os

import shotgun_api3
import config


class SGClient:
    def __init__(self):
        if os.environ.get("SGDESK_DEV") == "1":
            from sgdesk_dcc.devkit.mock_sg import MockShotgun
            self.sg = MockShotgun()
            self._owner = None
            return
        self.sg = shotgun_api3.Shotgun(
            config.SG_SITE,
            script_name=config.SG_SCRIPT_NAME,
            api_key=config.SG_SCRIPT_KEY,
        )
        self._owner = None

    # -- user / owner -----------------------------------------------------

    def resolve_owner(self, login):
        """Find the entity that sg_task_owner points to for this login."""
        self._owner = self.sg.find_one(
            config.TASK_OWNER_ENTITY,
            [[config.TASK_OWNER_MATCH_FIELD, "is", login]],
            [config.TASK_OWNER_MATCH_FIELD, "name"]
            if config.TASK_OWNER_ENTITY != "HumanUser"
            else ["login", "name"],
        )
        return self._owner

    @property
    def owner(self):
        return self._owner

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
            if not links or any(p["id"] == project["id"] for p in links):
                if sw.get("linux_path"):
                    out.append(sw)
        return out

    def my_tasks(self, project, statuses=None):
        if not self._owner:
            return []
        filters = [
            ["project", "is", {"type": "Project", "id": project["id"]}],
            [config.TASK_OWNER_FIELD, "is",
             {"type": self._owner["type"], "id": self._owner["id"]}],
        ]
        if statuses:
            filters.append(["sg_status_list", "in", statuses])
        return self.sg.find(
            "Task", filters, config.TASK_FIELDS,
            order=[{"field_name": "due_date", "direction": "asc"}],
        )
