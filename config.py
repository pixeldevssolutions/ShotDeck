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
    # Deep fields, needed to build the folder path without a second query.
    "entity.Shot.sg_sequence",
    "entity.Asset.sg_asset_type",
]

# Where a task's files live. Tokens: {project} (tank_name), {project_name},
# {sequence}, {shot}, {asset}, {asset_type}, {entity}, {step}.
ENTITY_PATH_TEMPLATES = {
    "Shot": "/jobs/{project}/sequences/{sequence}/shots/{shot}",
    "Asset": "/jobs/{project}/assets/{asset_type}/{asset}",
}

# Shortcuts listed under "Open folder". {step} is the pipeline step lowercased.
# Missing ones are greyed out rather than hidden, so it's obvious when a shot
# was never built out properly.
ENTITY_SUBFOLDERS = [
    ("maya scenes",     "maya/scenes"),
    ("maya scenes / {step}", "maya/scenes/{step}"),
    ("houdini hip",     "houdini/hip"),
    ("nuke comp",       "nuke/comp/scene"),
    ("nuke / {step}",   "nuke/{step}/scene"),
    ("blender scenes",  "blender/scenes"),
    ("3DE scene",       "3DE/scene"),
    ("plates",          "elements/plates"),
    ("elements",        "elements"),
    ("dailies",         "elements/dailies"),
    ("renders",         "nuke/renders"),
]

# Rocky 9 desktop: xdg-open picks the session's file manager. Override with
# SHOTDECK_FILE_MANAGER=nautilus (or dolphin, thunar, nemo) if that misfires.
FILE_MANAGER = os.environ.get("SHOTDECK_FILE_MANAGER", "xdg-open")

SOFTWARE_FIELDS = [
    "code", "sg_status_list", "image",
    "linux_path", "linux_args", "version",
    "projects", "engine",
    "sg_external_ui", "sg_file_ext", "sg_rez_packages",
]

PROJECT_FIELDS = ["name", "sg_status", "image", "sg_description", "tank_name"]

# Field on Software holding the rez request, e.g. "maya-2024 keentools-6.2".
SOFTWARE_REZ_FIELD = "sg_rez_packages"
# Package appended to every rez request so in-DCC tools can `import
# shotdeck_context`. Set to "" to stop injecting it.
REZ_CONTEXT_PACKAGE = "shotdeck_context"

# -- standalone publish ----------------------------------------------------

# Field on Version linking it back to the Task. Stock ShotGrid uses sg_task.
VERSION_TASK_FIELD = "sg_task"
# Field linking the Version to the Shot or Asset.
VERSION_ENTITY_FIELD = "entity"
# Field the media is uploaded to. This is what the SG player streams.
VERSION_MEDIA_FIELD = "sg_uploaded_movie"
# Status a freshly published Version gets. "" leaves it at the site default.
VERSION_STATUS = "rev"

# Extensions treated as movies rather than stills.
MOVIE_EXTENSIONS = {
    ".mov", ".mp4", ".mxf", ".avi", ".mkv", ".webm", ".m4v", ".r3d",
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr", ".dpx", ".tga", ".bmp",
}

# rez entry point. Set SHOTDECK_REZ_EXECUTABLE to an absolute path when the
# artist's login shell does not put rez on PATH.
REZ_EXECUTABLE = os.environ.get("SHOTDECK_REZ_EXECUTABLE", "rez")

# Released DCC packages, one folder per package and per version inside it.
# The right-click menu on a task is built from this tree.
DCC_PACKAGES_ROOT = os.environ.get(
    "SHOTDECK_DCC_ROOT", "/software/packages/dcc")

# Fallback for checking whether a package exists, used only when
# REZ_PACKAGES_PATH is not already in the environment. Mirrors the search
# path in /software/pipeline/init_source/configs/rezconfig.py.
REZ_PACKAGE_PATHS = [
    "/software/packages/plugins",
    "/software/packages/tools",
    "/software/packages/dcc",
    "/software/packages/libs",
    "/software/packages/external",
    "/software/packages/dev",
    os.path.expanduser("~/packages"),
]

# Executable to run inside `rez env <package>`, when it is not just the package
# name. Add an entry here whenever a package's alias differs from its name.
DCC_COMMANDS = {
    "3de": "DD3DE4",
    "mochapro": "mocha",
    "openrv": "rv",
    "silhouette": "sfx",
}

# Pretty names for the menu. Anything absent is title-cased.
DCC_LABELS = {
    "3de": "3DEqualizer",
    "openrv": "OpenRV",
    "mochapro": "Mocha Pro",
    "pureref": "PureRef",
    "meshlab": "MeshLab",
}

# Per-project env YAMLs live here; falls back to default.yml
ENVS_DIR = os.path.join(os.path.dirname(__file__), "envs")

APP_TITLE = "PixelDesk"
