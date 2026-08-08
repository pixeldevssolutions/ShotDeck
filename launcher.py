import os
import shlex
import subprocess
import sys

import config
import context as ctx_mod
from env_resolver import build_env


def launch(project, software, login=None, email=None, task=None):
    """Start a DCC for this project, inside a rez environment when one is set.

    `task` is the ShotGrid Task the artist selected, or None. Either way a
    context file is written and pointed at by SHOTDECK_CONTEXT_FILE, so
    in-DCC publish tools always have something to read.
    """
    ctx = ctx_mod.build(project, software, task, login, email)
    ctx_path = ctx_mod.write(ctx)

    extra = {
        "SGDESK_USER": login or "",          # kept for existing envs/*.yml
        "SGDESK_USER_EMAIL": email or "",
    }
    extra.update(ctx_mod.env(ctx, ctx_path))
    env = build_env(project, software, extra=extra)

    if software.get("sg_external_ui"):
        return _launch_external_ui(software, env)

    cmd = _build_command(software)
    proc = subprocess.Popen(
        cmd,
        env=env,
        start_new_session=True,   # survive ShotDeck exiting
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def _build_command(software):
    """Resolve the Software entity into an argv list.

    With rez packages set, the app runs as `rez env <pkgs> -- <cmd> <args>`.
    `linux_path` may then be a bare command name (`maya`) rather than an
    absolute path, since the rez packages put it on PATH; without rez packages
    it must be a real path, because nothing else resolves it.
    """
    rez_pkgs = _rez_packages(software)
    exe = (software.get("linux_path") or "").strip()
    args = shlex.split(software.get("linux_args") or "")

    if not exe:
        if not rez_pkgs:
            raise RuntimeError(
                f"Software '{software['code']}' has neither linux_path nor "
                f"{config.SOFTWARE_REZ_FIELD} set — nothing to launch")
        # No explicit command: rely on the package's own alias, named after
        # the Software code (rez env keentools -- keentools).
        exe = software["code"].lower().replace(" ", "_")

    if rez_pkgs:
        return ["rez", "env"] + rez_pkgs + ["--", exe] + args
    return [exe] + args


def _rez_packages(software):
    """Requested rez packages, with the context package always included."""
    pkgs = (software.get(config.SOFTWARE_REZ_FIELD) or "").split()
    if not pkgs:
        return []
    if config.REZ_CONTEXT_PACKAGE and not any(
            p.split("-")[0] == config.REZ_CONTEXT_PACKAGE for p in pkgs):
        pkgs.append(config.REZ_CONTEXT_PACKAGE)
    return pkgs


def _launch_external_ui(software, env):
    """DCC has no Python API — start the companion app instead.
    The companion inherits the full project env and launches the exe itself."""
    name = software["code"].lower().replace(" ", "_")
    ext = software.get("sg_file_ext") or "prj"
    cmd = [
        sys.executable, "-m", "sgdesk_dcc.external.app",
        "--name", name, "--ext", ext,
        "--exe", software["linux_path"],
        "--args", software.get("linux_args") or "",
    ]
    proc = subprocess.Popen(
        cmd, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.pid
