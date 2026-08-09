# PixelDesk — ShotGrid Desktop clone

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
project, entity, task and user being published against, suggests the next
`<entity>_<step>_v###` name, previews the media, and takes an optional
description.

It creates a Version linked to the task and uploads the media to
`sg_uploaded_movie`; stills also get a thumbnail. The field names are all
configurable in `config.py` (`VERSION_TASK_FIELD`, `VERSION_ENTITY_FIELD`,
`VERSION_MEDIA_FIELD`, `VERSION_STATUS`).

The ShotGrid script user needs permission to create Versions and upload to the
media field.

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
