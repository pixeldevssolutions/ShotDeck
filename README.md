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
