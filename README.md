# PixelDesk — Custom ShotGrid Desktop 

Project picker → per-project app launcher → launches DCCs on Rocky Linux with
project-level environment injected → "My Tasks" tab filtered by the studio's
custom `sg_assigned_to` field (not `task_assignees`).

## Run
```bash
export SG_SITE=https://yourstudio.shotgrid.autodesk.com
export SG_SCRIPT_NAME=sgdesk
export SG_SCRIPT_KEY=xxxx
pip install -r requirements.txt
python -m sgdesk.main
```

## How pieces map to ShotGrid
- **Projects page**: `Project` where `sg_status=Active`, tile grid like SG Desktop.
- **Apps tab**: `Software` entities with `sg_status_list=act` and a `linux_path`.
  Global software (no `projects` links) shows everywhere; project-linked software
  only shows on its projects.
- **My Tasks tab**: `Task` filtered on `sg_assigned_to` = current owner entity.
  The owner is looked up by **email address** (`HumanUser.email`), not login.
  The address defaults to `<os-login>@5and8.ai`; set `SGDESK_USER_EMAIL` to
  override it, or `SGDESK_EMAIL_DOMAIN` to change just the domain. If
  `sg_assigned_to` links to a CustomEntity instead of HumanUser, change
  `TASK_OWNER_ENTITY` / `TASK_OWNER_MATCH_FIELD` in `config.py` — nothing else
  changes.

## Environment injection
`env_resolver.build_env()` merges, in order:
1. current `os.environ`
2. `envs/default.yml` → `env:` then `software:<code>:`
3. `envs/<tank_name>.yml` → same sections
4. per-launch extras (`SGDESK_USER`, `SGDESK_USER_EMAIL`, `SGDESK_PROJECT_*`)

Tokens `{PROJECT_NAME}`, `{PROJECT_CODE}`, `{PROJECT_ID}` expand in values.
A key ending in `+` prepends to the existing var (`PYTHONPATH+`).

`launcher.launch()` runs `linux_path linux_args` via `subprocess.Popen` with the
merged env and `start_new_session=True` so DCCs survive PixelDesk closing.

## Launching through rez

Set `sg_rez_packages` on the Software entity to a rez request, e.g.
`maya-2024 keentools-6.2`. The app is then started as:

```
rez env <sg_rez_packages> shotdeck_context -- <linux_path> <linux_args>
```

With rez packages set, `linux_path` may be a bare command name (`maya`) because
the packages put it on `PATH`; if it is left empty, the Software `code`
lowercased is used as the command, so a package publishing a `keentools` alias
needs no path at all. Without rez packages, `linux_path` must be a real absolute
path — nothing else resolves it.

`shotdeck_context` is appended to every rez request automatically (set
`REZ_CONTEXT_PACKAGE = ""` in `config.py` to stop that).

### Building a rez package

Studio convention, using KeenTools as the example:

```
dev/KeenTools/            <- package folder, named after the package
    KeenTools6.2/         <- the DCC or plugin payload
    package.py            <- name, version, variants, commands()
    REZ_INSTALLER.py      <- copies the payload into REZ_BUILD_INSTALL_PATH
```

`package.py` sets `build_command = "python {root}/REZ_INSTALLER.py"`, and
`variants` drives the platform/arch folders that get created. Then, from inside
the package folder:

```bash
rez build -ic                 # installs to ~/packages
# new terminal:
rez env keentools             # verify it resolves and runs
git push                      # if the package has a repo
rez release .                 # installs to /software/packages (set in rez config)
# rename or remove the local ~/packages copy, then re-test rez env
```

`rez/shotdeck_context/` in this repository is a working example of that layout —
build and release it once, and every DCC launched by ShotDeck can import it.

## Standalone publish

Right-click a task → **Publish → Standalone Publish…** to upload a movie or
image to ShotGrid as a Version without opening a DCC. The dialog shows the
project, entity, task, department and user being published against, suggests
the next `<entity>_<step>_v###` name, inspects and previews the media, and
takes an optional description.

It creates a Version linked to the task and uploads the media to
`sg_uploaded_movie`; stills also get a thumbnail. The field names are all
configurable in `config.py` (`VERSION_TASK_FIELD`, `VERSION_ENTITY_FIELD`,
`VERSION_MEDIA_FIELD`, `VERSION_STATUS`).

### Who publishes

Every API call authenticates as the script user in `SG_SCRIPT_NAME`
(`SG_daemon`), which is the whole reason artists need no ShotGrid seat. The
Version's `user` field still credits the artist ShotDeck resolved from their
email address at startup. Those are two different identities and
`SGClient.create_version` is where that is enforced — nothing sets `user` to
the script. The result panel names both, so it is obvious from the Version
which account uploaded it.

The script user needs create permission on Version and upload permission on the
media field. Nothing prompts an artist for credentials, and the key is only
ever read from the environment.

### How it is put together

```
ui/publish_dialog.py   input, preview, progress, result — no ShotGrid calls
publish_service.py     validate, inspect, name, create, upload, clean up
media_inspector.py     ffprobe / Qt, resolution, fps, duration, codec
sg_client.py           the one ShotGrid client, script-authenticated
```

`publish_service` imports no Qt, so the whole publish is testable headlessly;
the dialog does no ShotGrid work of its own.

### What it refuses to do

- **Overwrite a Version.** The name is checked against the task's existing
  versions while you type, and again against the server immediately before the
  create — two artists reaching `v004` at the same moment is a real thing, and
  the server's answer is the authoritative one.
- **Publish something that is not media.** The formats come from
  `config.MEDIA_TYPES`, which is also what fills the file dialog filter and
  routes dropped files.
- **Leave half a publish behind.** If the upload fails or the artist cancels
  after the Version was created, the Version is deleted again.

Large uploads run on the thread pool, so the window stays responsive. The
progress bar is deliberately indeterminate: `shotgun_api3.upload()` exposes no
progress callback, so a percentage or an ETA would be invented. The stage line
names the file and its size instead.

### Drag and drop

Files can be dropped anywhere on the dialog. The extension decides where a
dropped file lands: a movie or image fills the media field, a known scene
extension fills the work file field, and anything else fills whichever is still
empty. Dropping two files at once — the render and the scene that made it — is
handled in one go.

### Drag and drop

Files can be dropped anywhere on the dialog. The extension decides where a
dropped file lands: a movie or image fills the media field, a known scene
extension fills the work file field, and anything else fills whichever is still
empty. Dropping two files at once — the render and the scene that made it — is
handled in one go.

### The work file

Below the media field is an optional **work file**: the DCC scene the media came
from (`.nk`, `.ma`, `.hip`, `.blend`, …; the full list with its labels is
`config.WORKFILE_EXTENSIONS`). It is registered after the media, so a problem
with it never costs you the Version — the dialog reports it and stays open
instead.

`config.WORKFILE_MODE` decides what registering means:

| Mode | What happens | Needs |
|---|---|---|
| `published_file` (default) | Creates a `PublishedFile` pointing at the file where it already lives on `/jobs`, linked to the Version, task and entity. Nothing is uploaded. | Create on `PublishedFile`, and a LocalStorage covering the path for the link to resolve |
| `attachment` | Uploads the scene file onto the Version as an attachment. | Upload on `Version` |
| `path_only` | Records the path and nothing else. | Write on `Version` |

In `published_file` mode the extension is matched against
`config.PUBLISHED_FILE_TYPES` to set `published_file_type`; an unknown extension
just leaves it unset. If the site has no LocalStorage covering the path, the
create is retried without the path link and the path goes in the description, so
the registration still happens.

The path is also written onto the Version itself — to
`config.VERSION_WORKFILE_FIELD` if you point it at a text field, otherwise
appended to the description.

## Version browser

Right-click a task → **Versions → View Versions…** to see what has already been
published on that shot or asset. The scope switch at the top narrows it to the
one task.

Filtering is done by ShotGrid, not in the client: department, artist, status,
date range and the search box all become query filters (`version_query.py`),
and results arrive `config.VERSION_PAGE_SIZE` at a time with a Load more button.
Search is debounced, so typing does not fire a query per keystroke.

- **Department** comes from the site's own `Step` entities, filtered to the
  entity type being browsed.
- **Status** comes from the `Version.sg_status_list` schema, so it is whatever
  this site actually uses.
- **Artist** is built from the versions on screen rather than by fetching every
  user on the site.
- **Sorting** covers date both ways, version name, artist, department and
  status; the default is newest first.

Selecting a version shows its thumbnail and the fields the site actually filled
in — nothing is displayed as a dash. A version whose `sg_path_to_movie` exists
on this machine can be played in place. Right-click gives Open in ShotGrid and
Copy media path.

## Tests

```bash
python tests/run.py            # everything
python tests/run.py publish    # modules matching "publish"
```

No pytest, and no network: `tests/fakes.py` implements the slice of the
ShotGrid API the client uses, so the real `SGClient`, `PublishService` and
widgets are what run. UI tests force Qt's offscreen platform, so this works
over ssh.

## Publish context inside the DCC

Every launch writes a JSON context file and exports `SHOTDECK_CONTEXT_FILE`
pointing at it, plus flat `SHOTDECK_*` variables (`SHOTDECK_TASK_ID`,
`SHOTDECK_ENTITY_TYPE`, `SHOTDECK_ENTITY_ID`, `SHOTDECK_STEP`,
`SHOTDECK_PROJECT_ID`, …) for shell scripts and rez `commands()` blocks.

The task comes from the row selected in the **My Tasks** tab; the bar under the
tabs shows which task an app will launch against. Launching with nothing
selected is allowed — the context is written with `task: null`.

In-DCC tools should use the package rather than reading the variables:

```python
import shotdeck_context

ctx = shotdeck_context.get()
if ctx.has_task:
    publish(task=ctx.task_id, entity=(ctx.entity_type, ctx.entity_id))
else:
    warn("Launched without a task — pick one in ShotDeck and relaunch.")
```

`get()` never raises: outside a ShotDeck launch it returns an empty `Context`
that is falsey, so tools degrade instead of tracebacking at an artist.
