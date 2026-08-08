# Deploying PixelDesk (sgdesk) on Rocky Linux 9

Target: Rocky Linux 9.x, X11 or Wayland desktop, artists launching DCCs from a
shared studio mount. Written 2026-08-08 against the code described in
`HANDOFF.md`. Nothing here has been executed yet — treat it as a plan to verify,
not a transcript.

---

## 0. Fix these before deploying

Three items in `HANDOFF.md` will bite during deployment specifically:

1. **`config.py:5` has a hardcoded ShotGrid script key.** Do not ship it to a
   multi-user machine. Make it environment-only and rotate the key (step 5
   below assumes this is done).
2. **The README run command (`python -m sgdesk.main`) does not work** — imports
   are flat. The wrapper script in step 6 works around it by setting the working
   directory; the cleaner fix is to convert to package-relative imports.
3. **`sgdesk_dcc` does not exist.** Any Software entity with `sg_external_ui`
   set will fail to launch, and `SGDESK_DEV=1` will crash. Either write the
   package or make sure no Software entity has `sg_external_ui` set at go-live.

---

## 1. System packages

Rocky 9 ships Python 3.9 as `python3`. PySide6 runs on it, but 3.11 from
AppStream is the safer target and is packaged by Rocky:

```bash
sudo dnf install -y python3.11 python3.11-pip
```

Qt's `xcb` platform plugin has runtime library dependencies that are **not**
pulled in by the PySide6 wheel. Missing them produces the classic
`qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` failure:

```bash
sudo dnf install -y \
    libxkbcommon-x11 libxkbcommon \
    xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
    libX11-xcb libXrandr libXcursor libXi libXtst \
    mesa-libGL mesa-libEGL \
    fontconfig dbus-libs
```

On a minimal/headless-ish install also add `dejavu-sans-fonts` — Qt renders
blank labels with no fonts present.

Wayland sessions: PySide6 will use the `wayland` plugin if
`QT_QPA_PLATFORM=wayland`, but XWayland via `xcb` is the better-tested path for
DCC interop. Force it in the wrapper if you hit issues:
`export QT_QPA_PLATFORM=xcb`.

---

## 2. Install location

Two workable choices:

| Layout | When to use |
|---|---|
| `/opt/pixeldesk` on each workstation | Small fleet, or workstations without a reliable tools mount. Update via Ansible/rsync. |
| `/mnt/projects/tools/pixeldesk` (shared NFS) | Preferred for a studio — one place to update, everyone picks it up on next launch. |

The shared mount is assumed below. Note the source root is the **inner**
directory (see `HANDOFF.md` section 2) — copy that, not the wrapper:

```bash
sudo mkdir -p /mnt/projects/tools/pixeldesk
sudo rsync -a --delete \
    --exclude '__pycache__' --exclude '.idea' --exclude 'sgdesk/' \
    /path/to/sgdesk/sgdesk/ /mnt/projects/tools/pixeldesk/app/
```

The `--exclude 'sgdesk/'` matters: the nested `sgdesk/` directory inside the
source root is a Windows virtualenv, not code, and must never be copied to Linux.

---

## 3. Virtual environment

Build the venv **on Rocky 9**, never copy the Windows one:

```bash
python3.11 -m venv /mnt/projects/tools/pixeldesk/venv
/mnt/projects/tools/pixeldesk/venv/bin/pip install --upgrade pip
/mnt/projects/tools/pixeldesk/venv/bin/pip install -r /mnt/projects/tools/pixeldesk/app/requirements.txt
```

`requirements.txt` pins `PySide6>=6.5`, `shotgun-api3`, `PyYAML`.

**Check the `shotgun-api3` install.** Autodesk distributes the official API from
GitHub, and the PyPI name has historically not been the canonical source. If the
PyPI package is not the Autodesk one, install from the tag instead:

```bash
/mnt/projects/tools/pixeldesk/venv/bin/pip install \
    git+https://github.com/shotgunsoftware/python-api.git@v3.4.0
```

Verify before going further:

```bash
/mnt/projects/tools/pixeldesk/venv/bin/python -c \
  "import shotgun_api3, PySide6, yaml; print(shotgun_api3.__version__)"
```

If the venv lives on NFS, pin it to a real filesystem instead
(`/opt/pixeldesk/venv`) if you see slow start-up — Python import over NFS is
noticeably worse than the app itself.

---

## 4. ShotGrid script user

In ShotGrid Admin → Scripts, confirm or create a script user for this tool, and
grant it a permission role that can **read** `Project`, `Software`, `Task`,
`HumanUser`. PixelDesk never writes, so a read-only role is correct and is the
right blast radius for a credential that sits on artist workstations.

Rotate the key that is currently in `config.py` — assume it is compromised.

---

## 5. Credentials on the host

Do not put the key in a world-readable file, and do not put it in the shared
mount. One file per workstation, root-owned:

```bash
sudo install -d -m 0755 /etc/sgdesk
sudo tee /etc/sgdesk/sgdesk.env >/dev/null <<'EOF'
SG_SITE=https://5and8.shotgrid.autodesk.com
SG_SCRIPT_NAME=SG_daemon
SG_SCRIPT_KEY=<rotated-key-here>
EOF
sudo chmod 0644 /etc/sgdesk/sgdesk.env
```

`0644` is deliberate: artists run the app as themselves, so the process must be
able to read it. That means **any user on the box can read the key** — which is
exactly why the script user must be read-only, and why the broker approach used
by the sibling `vfx-desktop` project (one process holds the only credential, the
UI asks it for data) is the better long-term design. Note this as a known
limitation at go-live rather than discovering it during an audit.

---

## 6. Wrapper script

This works around the flat-import problem by running from inside the source root.

`/usr/local/bin/pixeldesk`:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=/mnt/projects/tools/pixeldesk/app
VENV=/mnt/projects/tools/pixeldesk/venv

set -a
[ -r /etc/sgdesk/sgdesk.env ] && . /etc/sgdesk/sgdesk.env
set +a

: "${SG_SCRIPT_KEY:?SG_SCRIPT_KEY is not set — check /etc/sgdesk/sgdesk.env}"

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

cd "$APP_ROOT"
exec "$VENV/bin/python" main.py "$@"
```

```bash
sudo chmod 0755 /usr/local/bin/pixeldesk
```

If Linux account names do not match the ShotGrid email local part (open question
2 in `HANDOFF.md`), the app resolves the wrong user and My Tasks comes up empty
with no error. Handle it centrally rather than per user — either add a mapping
to `envs/default.yml`, or export `SGDESK_USER_EMAIL` in the wrapper for the
affected accounts.

---

## 7. Desktop entry

`/usr/share/applications/pixeldesk.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=PixelDesk
Comment=Project and application launcher
Exec=/usr/local/bin/pixeldesk
Icon=pixeldesk
Terminal=false
Categories=Graphics;AudioVideo;
```

```bash
sudo update-desktop-database /usr/share/applications
```

Drop an icon at `/usr/share/icons/hicolor/256x256/apps/pixeldesk.png` and run
`sudo gtk-update-icon-cache /usr/share/icons/hicolor` if you want the icon to
resolve.

---

## 8. Project environment YAMLs

`envs/default.yml` and `envs/<tank_name>.yml` are read from `ENVS_DIR`, which is
resolved relative to `config.py` — so they live inside the deployed `app/`
directory and update with it. If per-project environments should be editable by
pipeline TDs without redeploying the app, that is a code change
(`ENVS_DIR = os.environ.get("SGDESK_ENVS_DIR", ...)`) worth making before
go-live rather than after.

Remember `<tank_name>` is the project's ShotGrid `tank_name`, falling back to a
lowercased, underscored project name.

---

## 9. rez and the DCCs

If any Software entity sets `sg_rez_packages`, `launcher.py` wraps the command as
`rez env <pkgs> -- <exe> <args>`. So `rez` must be **on PATH for the artist's
login shell**, not just root's, on every workstation. Verify with
`su - someartist -c 'which rez'`.

Also confirm for each Software entity in ShotGrid:

- `linux_path` points at a path that exists on the workstation (it is used
  verbatim — no resolution, no PATH lookup)
- `sg_status_list` is `act`, or the app will not list it
- `projects` links are right: empty means the Software shows on every project

DCCs are launched with `start_new_session=True`, so they correctly survive
PixelDesk exiting. Their stdout and stderr go to `DEVNULL` — meaning **a DCC that
fails to start fails silently**. When debugging a launch, run the same command by
hand from a terminal rather than trying to read logs that do not exist.

---

## 10. SELinux and mounts

Rocky 9 runs SELinux enforcing by default. A normal userspace app launching other
userspace apps needs no policy work. Two things that do come up:

- Projects on NFS: if home directories or the tools tree are NFS-mounted, check
  `getsebool -a | grep nfs` and set `use_nfs_home_dirs` if home dirs are remote.
- If a launch fails with no obvious cause, check for denials before assuming a
  bug: `sudo ausearch -m AVC -ts recent`.

Mount the projects tree before anyone logs in — an autofs or `/etc/fstab` entry
for `/mnt/projects`, not a manual mount.

---

## 11. Verification checklist

Run in order on one pilot workstation, as a real artist account, not root:

1. `pixeldesk` starts and the window appears (catches all of section 1).
2. The project grid populates → the ShotGrid credential and network path work.
3. The header shows the expected email address → `current_user_email()` is
   deriving it correctly for this account.
4. Open a project → the Apps tab lists the expected Software.
5. **My Tasks shows tasks.** This is the single most likely thing to be wrong —
   it is the untested `sg_assigned_to` code path. If it is empty, work through
   open questions 1 and 2 in `HANDOFF.md`: is the field an entity link or a
   plain email string, and does this Linux account name match the email?
6. Launch a DCC. Confirm from a terminal that the environment actually arrived:
   `tr '\0' '\n' < /proc/<pid>/environ | grep SGDESK_`.
7. Quit PixelDesk with the DCC still open — the DCC must survive.

Only after all seven pass on the pilot box should this be rolled out to the
fleet.

---

## 12. Updating a deployment

With the shared-mount layout, an update is the rsync in step 2 plus a venv
`pip install -r requirements.txt` if dependencies changed. Artists pick it up on
their next launch; running instances are unaffected.

Because this is not a git repository yet, there is no way to tell what version a
workstation is running or to roll back. Run `git init` and deploy from a tag
before this goes to more than a couple of machines.
