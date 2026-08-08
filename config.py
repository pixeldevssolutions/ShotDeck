import os

SG_SITE = os.environ.get("SG_SITE", "https://5and8.shotgrid.autodesk.com")
SG_SCRIPT_NAME = os.environ.get("SG_SCRIPT_NAME", "SG_daemon")
SG_SCRIPT_KEY = os.environ.get("SG_SCRIPT_KEY", "ja?loxpbfv6fpxhCflhehsula")

# Custom ownership field on Task. Studio uses this instead of task_assignees.
TASK_OWNER_FIELD = "sg_task_owner"
# Entity type the field links to. Change to "CustomEntity03" etc. if it's not HumanUser.
TASK_OWNER_ENTITY = "HumanUser"
# Field on the owner entity used to match the current user's login.
TASK_OWNER_MATCH_FIELD = "login"   # for CustomEntity use e.g. "sg_login" or "code"

TASK_FIELDS = [
    "content", "sg_status_list", "due_date",
    "entity", "step", "project", TASK_OWNER_FIELD,
]

SOFTWARE_FIELDS = [
    "code", "sg_status_list", "image",
    "linux_path", "linux_args", "version",
    "projects", "engine",
    "sg_external_ui", "sg_file_ext", "sg_rez_packages",
]

PROJECT_FIELDS = ["name", "sg_status", "image", "sg_description", "tank_name"]

# Per-project env YAMLs live here; falls back to default.yml
ENVS_DIR = os.path.join(os.path.dirname(__file__), "envs")

APP_TITLE = "PixelDesk"
