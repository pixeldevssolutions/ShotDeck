import os

SG_SITE = os.environ.get("SG_SITE", "https://5and8.shotgrid.autodesk.com")
SG_SCRIPT_NAME = os.environ.get("SG_SCRIPT_NAME", "SG_daemon")
# No default: a script key must never live in the source of a public repository.
SG_SCRIPT_KEY = os.environ.get("SG_SCRIPT_KEY", "")

# Custom assignment field on Task. Studio uses this instead of task_assignees.
TASK_OWNER_FIELD = "sg_assigned_to"

# sg_assigned_to is a plain String field on this site, NOT an entity link
# (confirmed 2026-08-08: passing an entity dict fails with
# "expected [String, NilClass] data type(s) but got Hash").
# Set True only if a site changes it to a real entity link field.
TASK_OWNER_IS_ENTITY = False

# Entity type looked up to identify the user. Change to "CustomEntity03" etc.
# if the studio does not use HumanUser.
TASK_OWNER_ENTITY = "HumanUser"
# Field on that entity matched against the current user's email address.
TASK_OWNER_MATCH_FIELD = "email"   # for CustomEntity use e.g. "sg_email"

# String mode only: which field of the resolved owner entity holds the value
# that Task.sg_assigned_to actually stores. Set to "email" if tasks store
# addresses, "name" if they store "Firstname Lastname", "login" for logins.
TASK_OWNER_STRING_FIELD = "email"
# Comparison operator for the string filter. Use "contains" if one task can
# list several people in the same string.
TASK_OWNER_STRING_OP = "is"

# Email domain used to derive the current user's address from their OS login
# (jitesh -> jitesh@5and8.ai). Override the whole address with SGDESK_USER_EMAIL
# when the Linux account name doesn't match the ShotGrid address.
USER_EMAIL_DOMAIN = os.environ.get("SGDESK_EMAIL_DOMAIN", "5and8.ai")


def current_user_email(login):
    """Address to match against TASK_OWNER_MATCH_FIELD for this session."""
    return (os.environ.get("SGDESK_USER_EMAIL") or f"{login}@{USER_EMAIL_DOMAIN}").strip()

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
