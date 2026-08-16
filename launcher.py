import os
import shlex
import shutil
import subprocess
import sys

import applog
import config
import context as ctx_mod
import rez_scan
from env_resolver import build_env

log = applog.get()


class LaunchError(RuntimeError):
    """Raised when a launch cannot even be attempted."""


def launch(project, software, login=None, email=None, task=None):
    """Start a DCC for this project, inside a rez environment when one is set.

    `task` is the ShotGrid Task the artist selected, or None. Either way a
    context file is written and pointed at by SHOTDECK_CONTEXT_FILE, so
    in-DCC publish tools always have something to read.

    Returns (pid, log_path). The process writes its stdout and stderr to
    log_path -- a file rather than a pipe, so a DCC is never blocked by a full
    pipe buffer after ShotDeck exits.
    """
    ctx = ctx_mod.build(project, software, task, login, email)
    ctx_path = ctx_mod.write(ctx)

    extra = {
        "SGDESK_USER": login or "",          # kept for existing envs/*.yml
        "SGDESK_USER_EMAIL": email or "",
    }
    extra.update(ctx_mod.env(ctx, ctx_path))
    extra.update(_tools_paths(software))
    env = build_env(project, software, extra=extra)

    name = software.get("code") or "app"
    task_desc = f"task {task['id']} ({task.get('content', '')})" if task \
        else "no task"
    log.info("launching %s for %s / %s", name, project["name"], task_desc)
    log.debug("context file: %s", ctx_path)

    if software.get("sg_external_ui"):
        cmd = _external_ui_command(software)
    else:
        cmd = _build_command(software)

    _preflight(cmd, software)

    log_path = applog.launch_log_path(name)
    log.info("command: %s", _quote(cmd))
    log.info("output:  %s", log_path)

    with open(log_path, "wb") as out:
        out.write(_log_header(cmd, env, ctx, log_path).encode())
        out.flush()
        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                start_new_session=True,   # survive ShotDeck exiting
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        except OSError as e:
            log.error("could not start %s: %s", cmd[0], e)
            raise LaunchError(
                f"Could not start {cmd[0]}: {e}\n\nCommand:\n{_quote(cmd)}")

    log.info("started %s with pid %s", name, proc.pid)
    return proc.pid, log_path


def launch_package(project, package, version=None, task=None,
                   login=None, email=None, extra_packages=()):
    """Launch a DCC discovered in the rez package tree, against a task.

    Runs `rez env <package>-<version> shotdeck_context -- <command>` in one
    shot: the command is passed to rez, so nothing has to be typed once the
    environment resolves.
    """
    software = {
        "code": package,
        "version": version or "",
        config.SOFTWARE_REZ_FIELD: " ".join(
            [rez_scan.request(package, version)] + list(extra_packages)),
        "linux_path": rez_scan.command_for(package),
        "linux_args": "",
    }
    return launch(project, software, login=login, email=email, task=task)


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
            raise LaunchError(
                f"Software '{software['code']}' has neither linux_path nor "
                f"{config.SOFTWARE_REZ_FIELD} set — nothing to launch")
        # No explicit command: rely on the package's own alias, named after
        # the Software code (rez env keentools -- keentools).
        exe = software["code"].lower().replace(" ", "_")

    if rez_pkgs:
        return [config.REZ_EXECUTABLE, "env"] + rez_pkgs + ["--", exe] + args
    return [exe] + args


# (package, what is lost when it has not been released yet)
_INJECTED_PACKAGES = [
    (config.REZ_CONTEXT_PACKAGE,
     "In-DCC tools must fall back to the SHOTDECK_* variables"),
    (config.REZ_DCC_PACKAGE,
     "The ShotDeck menu will not appear inside the DCC"),
]


def _rez_packages(software):
    """Requested packages, plus ShotDeck's own when they are released.

    Asking for a package that doesn't exist makes rez reject the whole resolve,
    so an unbuilt shotdeck_dcc would block every launch. Both are therefore
    optional: the launch still works, it just arrives with less.
    """
    pkgs = (software.get(config.SOFTWARE_REZ_FIELD) or "").split()
    if not pkgs:
        return []

    for name, cost in _INJECTED_PACKAGES:
        if not name or any(p.split("-")[0] == name for p in pkgs):
            continue
        if rez_scan.is_available(name):
            pkgs.append(name)
        else:
            log.warning(
                "%s is not released yet — launching without it. %s. Build it "
                "with: cd rez/%s && rez build -ic", name, cost, name)
    return pkgs


def _tools_paths(software):
    """PYTHONPATH/NUKE_PATH entries that make the in-DCC menu load itself.

    The rez package does this when it resolves, but it only resolves when the
    Software entity requests rez packages at all and the package has been
    released. A DCC launched straight from linux_path got neither, which is why
    the menu was missing until someone typed the import by hand. Pointing at
    the source tree costs nothing when the package is resolved: rez prepends
    its own copy, so its version is the one that wins.

    The "+" suffix is env_resolver's prepend syntax, so an existing PYTHONPATH
    from default.yml or a project YAML is kept.
    """
    code = (software.get("code") or "").lower().replace(" ", "")
    dcc_root = config.DCC_SOURCE_ROOT

    out = {}
    roots = [dcc_root, config.CONTEXT_SOURCE_ROOT]
    if code.startswith("maya"):
        # Maya runs any userSetup.py it finds on PYTHONPATH once the GUI is up.
        roots.append(os.path.join(dcc_root, "startup", "maya"))
    if code.startswith("nuke"):
        # Nuke reads init.py/menu.py off NUKE_PATH instead.
        nuke_startup = os.path.join(dcc_root, "startup", "nuke")
        if os.path.isdir(nuke_startup):
            out["NUKE_PATH+"] = nuke_startup

    roots = [p for p in roots if os.path.isdir(p)]
    if not roots:
        log.warning("in-DCC tools not found at %s — the ShotDeck menu will "
                    "not appear. Set SHOTDECK_DCC_SOURCE.", dcc_root)
        return out

    out["PYTHONPATH+"] = os.pathsep.join(roots)
    return out


def _preflight(cmd, software):
    """Fail with something readable instead of a silent non-start."""
    exe = cmd[0]
    if os.path.sep in exe:
        if not os.path.isfile(exe):
            raise LaunchError(
                f"linux_path does not exist on this machine:\n{exe}")
        if not os.access(exe, os.X_OK):
            raise LaunchError(f"linux_path is not executable:\n{exe}")
        return

    if shutil.which(exe) is None:
        if exe == config.REZ_EXECUTABLE:
            raise LaunchError(
                "rez is not on PATH for this session, so packaged apps cannot "
                "be launched.\n\nCheck that the artist's login shell sources "
                "the studio rez setup, or set SHOTDECK_REZ_EXECUTABLE to an "
                "absolute path.")
        raise LaunchError(f"Command not found on PATH: {exe}")


def _log_header(cmd, env, ctx, log_path):
    """Written at the top of every launch log, so it explains itself."""
    task = ctx.get("task") or {}
    shotdeck_env = "\n".join(
        f"  {k}={v}" for k, v in sorted(env.items())
        if k.startswith(("SHOTDECK_", "SGDESK_", "REZ_")))
    return (
        "# ShotDeck launch log\n"
        f"# {log_path}\n"
        f"# project : {ctx['project']['name']} (id {ctx['project']['id']})\n"
        f"# task    : {task.get('name') or '(none)'}"
        f"{' on ' + task['entity_name'] if task.get('entity_name') else ''}\n"
        f"# user    : {ctx['user']['login']} <{ctx['user']['email']}>\n"
        f"# command : {_quote(cmd)}\n"
        "#\n# environment passed in:\n"
        f"{shotdeck_env}\n"
        "# ---------------- process output below ----------------\n\n"
    )


def _quote(cmd):
    """The command as you would paste it into a shell."""
    try:
        return shlex.join(cmd)          # Python 3.8+
    except AttributeError:              # pragma: no cover - old interpreters
        return " ".join(shlex.quote(c) for c in cmd)


def _external_ui_command(software):
    """DCC has no Python API — start the companion app instead.
    The companion inherits the full project env and launches the exe itself."""
    name = software["code"].lower().replace(" ", "_")
    ext = software.get("sg_file_ext") or "prj"
    return [
        sys.executable, "-m", "sgdesk_dcc.external.app",
        "--name", name, "--ext", ext,
        "--exe", software["linux_path"],
        "--args", software.get("linux_args") or "",
    ]
