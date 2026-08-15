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

# Two kill-switches for isolating a hard crash on a workstation. Both are on
# by default; setting either to 0 removes a whole class of Qt work from the
# grids without changing anything else, which is the fastest way to tell a
# thumbnail/pixmap fault apart from a compositing one.
#   SHOTDECK_THUMBNAILS=0    no downloads, no QPixmap decoding, initials only
#   SHOTDECK_TILE_SHADOWS=0  no QGraphicsDropShadowEffect on the tiles
THUMBNAILS_ENABLED = os.environ.get("SHOTDECK_THUMBNAILS", "1") != "0"
TILE_SHADOWS_ENABLED = os.environ.get("SHOTDECK_TILE_SHADOWS", "1") != "0"

# How long the opening sequence runs before it will hand over, even when the
# window was ready sooner. The stages inside it are fractions of this, so one
# number retimes the whole thing. SHOTDECK_SPLASH_MS=0 skips it entirely, which
# is what you want when relaunching the app twenty times in a row.
SPLASH_MS = max(0, int(os.environ.get("SHOTDECK_SPLASH_MS", "6000")))

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
# Package that carries the in-DCC tools and their startup hooks. Appended the
# same way, so launching a DCC is the whole install -- no artist ever copies a
# userSetup.py. It requires shotdeck_context, so injecting it pulls in both.
# Set to "" to launch DCCs without the ShotDeck menu.
REZ_DCC_PACKAGE = "shotdeck_dcc"

# -- standalone publish ----------------------------------------------------

# Field on Version linking it back to the Task. Stock ShotGrid uses sg_task.
VERSION_TASK_FIELD = "sg_task"
# Field linking the Version to the Shot or Asset.
VERSION_ENTITY_FIELD = "entity"
# Field the media is uploaded to. This is what the SG player streams.
VERSION_MEDIA_FIELD = "sg_uploaded_movie"
# Status a freshly published Version gets. "" leaves it at the site default.
VERSION_STATUS = "rev"

# -- the version browser ---------------------------------------------------

# Fields read for the browser. Deep fields keep it to one query: the step comes
# off the linked task rather than a second round trip. A field the site does
# not have makes the whole find() fail, so anything non-stock added here has to
# exist -- VERSION_OPTIONAL_FIELDS below is the safe place for the rest.
# Only fields every ShotGrid site has. Anything a site might have renamed or
# removed belongs in VERSION_OPTIONAL_FIELDS below -- one unknown field fails
# the entire find(), which reads as "the version browser is broken".
VERSION_FIELDS = [
    "code", "description", "sg_status_list", "user", "created_by",
    "created_at", "updated_at", "entity", "sg_task", "image",
    "sg_task.Task.step",
    "sg_task.Task.content",
]

# Probed once against the schema and kept for the session if the site has them.
# These are stock fields, but stock is not the same as universal.
VERSION_OPTIONAL_FIELDS = [
    "sg_uploaded_movie", "sg_path_to_movie", "sg_path_to_frames",
    "sg_first_frame", "sg_last_frame", "frame_count", "frame_range",
]

# Versions fetched per page in the browser. The rest arrive on Load more.
VERSION_PAGE_SIZE = 100

# What "latest" means. ShotGrid's own timestamp, not the name: v010, v011, v002
# is a real publishing order and max(name) gets it wrong. Set to "code" only if
# a studio genuinely numbers versions in publish order.
LATEST_VERSION_FIELD = os.environ.get("SHOTDECK_LATEST_VERSION_FIELD",
                                      "created_at")

# Fields read for the Latest Version column. Deliberately small: this is one
# query across every task on the page.
LATEST_VERSION_FIELDS = [
    "code", "created_at", "sg_status_list", "sg_task", "entity", "user",
]

# How long the browser waits after a keystroke before querying ShotGrid.
SEARCH_DEBOUNCE_MS = 300

# -- notes -----------------------------------------------------------------
#
# ShotGrid's Note/Reply model is the whole model: a Note links to entities
# through note_links and replies are Reply rows pointing back at it. ShotDeck
# keeps no notes of its own.
NOTE_FIELDS = [
    "subject", "content", "user", "created_at", "updated_at",
    "note_links", "tasks", "sg_status_list", "attachments",
]
REPLY_FIELDS = ["content", "user", "created_at", "entity"]

# Read for note authors. permission_rule_set is ShotGrid's own idea of who
# somebody is (Artist, Manager, Client, ...) -- roles are not invented here.
USER_FIELDS = ["name", "email", "permission_rule_set", "image"]

# Notes are re-read on demand, never polled. This is the shortest gap between
# two refreshes that actually hits ShotGrid.
NOTES_MIN_REFRESH_SECONDS = 5

# -- the review inbox ------------------------------------------------------

# How far back "needs attention" looks. Everything older has been dealt with
# or has been overtaken by a newer version.
REVIEW_WINDOW_DAYS = int(os.environ.get("SHOTDECK_REVIEW_DAYS", "30"))

# Version statuses that mean somebody is waiting on the artist. Short codes,
# because that is what the site stores -- check them against the site's own
# status list before trusting this map (see HANDOFF).
# Deliberately NOT "rev": that is the status a fresh publish gets
# (VERSION_STATUS above), so treating it as an action item would mark every
# version the artist just published as needing their attention.
REVIEW_STATUS_TYPES = {
    "rej": "VERSION_REJECTED",
    "rrq": "REVISION_REQUESTED",
    "vwd": "REVISION_REQUESTED",     # "viewed, changes wanted" on some sites
}

# Which items have been looked at. Ids and timestamps, nothing else: ShotGrid
# has no per-user read flag ShotDeck is allowed to write.
REVIEW_READ_STATE_PATH = os.environ.get(
    "SHOTDECK_REVIEW_STATE",
    os.path.expanduser("~/.shotdeck/review_read.json"))

# Detail URL for an entity, used by "Open in ShotGrid".
def entity_url(entity_type, entity_id):
    return f"{SG_SITE.rstrip('/')}/detail/{entity_type}/{entity_id}"

# Extensions treated as movies rather than stills.
MOVIE_EXTENSIONS = {
    ".mov", ".mp4", ".mxf", ".avi", ".mkv", ".webm", ".m4v", ".r3d",
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr", ".dpx", ".tga", ".bmp",
}

# The one registry every extension check goes through. Add a format here and
# the file dialogs, the drop routing, the inspector and the publish validation
# all learn about it at once.
MEDIA_TYPES = {
    "movie": MOVIE_EXTENSIONS,
    "image": IMAGE_EXTENSIONS,
}


def media_kind(path):
    """"movie", "image", or "" for something we do not publish as media."""
    ext = os.path.splitext(path or "")[1].lower()
    for kind, extensions in MEDIA_TYPES.items():
        if ext in extensions:
            return kind
    return ""


def media_filter():
    """Qt file dialog filter string, built from the registry."""
    movies = " ".join(f"*{e}" for e in sorted(MOVIE_EXTENSIONS))
    images = " ".join(f"*{e}" for e in sorted(IMAGE_EXTENSIONS))
    return (f"Media ({movies} {images});;Movies ({movies});;"
            f"Images ({images});;All files (*)")


# Media inspection. ffprobe reads movies and stills alike, including EXR and
# DPX; without it the dialog falls back to Qt's image reader and file size.
FFPROBE = os.environ.get("SHOTDECK_FFPROBE", "ffprobe")
FFPROBE_TIMEOUT = 20

# -- where media is allowed to come from -----------------------------------
#
# A Version whose media sits on somebody's desktop is a Version nobody else can
# use: not the farm, not review, not the artist who picks the shot up next
# week. The project root is derived from ENTITY_PATH_TEMPLATES above rather
# than written out again here -- one convention, one place.

# What happens to media outside the approved locations:
#   "strict"        - refused. Nothing outside the project publishes.
#   "approved_only" - refused unless it is under one of APPROVED_MEDIA_ROOTS.
#   "warn"          - allowed, with a warning the artist has to acknowledge.
# Left at "warn" because the farm's mounts have not been confirmed yet; move it
# to "approved_only" once they have. See HANDOFF §5e.
PATH_POLICY = os.environ.get("SHOTDECK_PATH_POLICY", "warn")

# Locations outside the project that are still legitimate to publish from --
# shared plate stores, a vendor drop, a common elements library. {project} is
# the tank_name, {project_name} the display name. Set from the environment as
# a colon-separated list, or edit here.
APPROVED_MEDIA_ROOTS = [
    p for p in os.environ.get("SHOTDECK_APPROVED_MEDIA_ROOTS", "").split(os.pathsep)
    if p.strip()
]

# The root every project lives under, used to tell "another show" apart from
# "not a show at all". Taken from the shared prefix of ENTITY_PATH_TEMPLATES.
JOBS_ROOT = os.environ.get("SHOTDECK_JOBS_ROOT", "/jobs")

# Directories that are always the wrong place to publish from, matched on any
# path component. Local scratch that no render node can see.
UNSAFE_PATH_PARTS = [
    "desktop", "downloads", "documents",
    "tmp", "temp", "var/tmp", "appdata", "recycle.bin",
    "cache", "proxy_cache", ".cache", "trash",
]

# -- the optional work file ------------------------------------------------
#
# A publish may carry the DCC scene that produced the media (a .nk, .ma, .hip).
# It is always optional, and a failure to register it never fails the publish
# itself -- the Version and its media are already in ShotGrid by then.

# Scene files offered in the work file browser, mapped to a menu label.
WORKFILE_EXTENSIONS = {
    ".nk": "Nuke script",
    ".nknc": "Nuke script",
    ".ma": "Maya scene",
    ".mb": "Maya scene",
    ".hip": "Houdini scene",
    ".hipnc": "Houdini scene",
    ".hiplc": "Houdini scene",
    ".blend": "Blender scene",
    ".c4d": "Cinema 4D scene",
    ".3de": "3DEqualizer scene",
    ".mocha": "Mocha project",
    ".sfx": "Silhouette project",
    ".spp": "Substance Painter project",
    ".sbs": "Substance Designer graph",
    ".psd": "Photoshop document",
    ".aep": "After Effects project",
    ".katana": "Katana scene",
    ".usd": "USD scene",
    ".usda": "USD scene",
    ".usdc": "USD scene",
    ".zpr": "ZBrush project",
    ".ztl": "ZBrush tool",
}

# How the work file is registered in ShotGrid:
#   "published_file" - create a PublishedFile pointing at the file where it
#                      already lives on /jobs. Nothing is uploaded, which is
#                      the point: scene files are large and already on shared
#                      storage. Needs create permission on PublishedFile.
#   "attachment"     - upload the file itself onto the Version. Simplest
#                      permission-wise, but it copies the bytes into ShotGrid.
#   "path_only"      - write the path onto the Version and nothing else.
WORKFILE_MODE = os.environ.get("SHOTDECK_WORKFILE_MODE", "published_file")

# Fields used when WORKFILE_MODE is "published_file". All stock names.
PUBLISHED_FILE_TASK_FIELD = "task"
PUBLISHED_FILE_ENTITY_FIELD = "entity"
PUBLISHED_FILE_VERSION_FIELD = "version"
PUBLISHED_FILE_PATH_FIELD = "path"

# PublishedFileType looked up per extension. A type that does not exist on the
# site is skipped rather than created, so this list can be optimistic.
PUBLISHED_FILE_TYPES = {
    ".nk": "Nuke Script",
    ".nknc": "Nuke Script",
    ".ma": "Maya Scene",
    ".mb": "Maya Scene",
    ".hip": "Houdini Scene",
    ".hipnc": "Houdini Scene",
    ".blend": "Blender Scene",
    ".psd": "Photoshop Document",
    ".aep": "After Effects Project",
    ".usd": "USD Scene",
    ".usda": "USD Scene",
}

# Text field on Version holding the work file path, so the path is visible
# without opening the PublishedFile. Leave "" to append it to the description
# instead, which is the only text field every site is guaranteed to have.
VERSION_WORKFILE_FIELD = os.environ.get("SHOTDECK_VERSION_WORKFILE_FIELD", "")

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
