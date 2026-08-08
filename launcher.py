import shlex
import subprocess
import sys

from env_resolver import build_env


def launch(project, software, login=None, email=None):
    exe = software.get("linux_path")
    if not exe:
        raise RuntimeError(f"No linux_path set on Software '{software['code']}'")

    if software.get("sg_external_ui"):
        return _launch_external_ui(project, software, login, email)

    args = shlex.split(software.get("linux_args") or "")
    env = build_env(project, software, extra={
        "SGDESK_USER": login or "",
        "SGDESK_USER_EMAIL": email or "",
    })

    cmd = [exe] + args
    rez_pkgs = (software.get("sg_rez_packages") or "").split()
    if rez_pkgs:
        # rez resolves the DCC env; project env still rides on top via `env=`
        cmd = ["rez", "env"] + rez_pkgs + ["--"] + cmd

    proc = subprocess.Popen(
        cmd,
        env=env,
        start_new_session=True,   # survive sgdesk exit
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def _launch_external_ui(project, software, login, email=None):
    """DCC has no Python API — start the sgdesk_dcc companion app instead.
    The companion inherits the full project env and launches the exe itself."""
    env = build_env(project, software, extra={
        "SGDESK_USER": login or "",
        "SGDESK_USER_EMAIL": email or "",
    })
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
