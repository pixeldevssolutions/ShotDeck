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
    # Resolved once and passed on: _tools_paths() only fills what rez is not
    # already providing, and _build_command() must request exactly the same set.
    rez_pkgs = _rez_packages(software)
    tools = _tools_paths(software, rez_pkgs)
    extra.update(tools)
    env = build_env(project, software, extra=extra)

    name = software.get("code") or "app"
    task_desc = f"task {task['id']} ({task.get('content', '')})" if task \
        else "no task"
    log.info("launching %s for %s / %s", name, project["name"], task_desc)
    log.debug("context file: %s", ctx_path)

    if software.get("sg_external_ui"):
        cmd = _external_ui_command(software)
    else:
        cmd = _build_command(software, rez_pkgs)

    _preflight(cmd, software)
    _keep_tools_paths_through_rez(cmd, env, tools)

    log.info("in-DCC tools: %s", config.DCC_SOURCE_ROOT)
    log.info("context package: %s", config.CONTEXT_SOURCE_ROOT)
    log.info("PYTHONPATH: %s", env.get("PYTHONPATH", ""))
    if env.get("NUKE_PATH"):
        log.info("NUKE_PATH: %s", env["NUKE_PATH"])

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


def _build_command(software, rez_pkgs=None):
    """Resolve the Software entity into an argv list.

    With rez packages set, the app runs as `rez env <pkgs> -- <cmd> <args>`.
    `linux_path` may then be a bare command name (`maya`) rather than an
    absolute path, since the rez packages put it on PATH; without rez packages
    it must be a real path, because nothing else resolves it.
    """
    if rez_pkgs is None:
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


def _tools_paths(software, rez_pkgs=()):
    """PYTHONPATH/NUKE_PATH entries for whatever rez is not already providing.

    Rez first: a package in `rez_pkgs` is resolved by rez, which puts its own
    installed copy on PYTHONPATH and wires the host's startup mechanism, so
    ShotDeck adds nothing for it -- no second copy of the tools, no second
    userSetup.py, nothing that could shadow a released version.

    The source tree fills the gap until then. `shotdeck_dcc` is only injected
    into a request when the Software entity asks for rez packages at all and
    the package has been built (see _rez_packages), so a DCC launched straight
    from linux_path, or launched before the packages are released, gets nothing
    in-DCC -- which is why the menu was missing until someone typed the import
    by hand.

    The "+" suffix is build_env()'s own prepend syntax -- it strips the "+" and
    puts the value in front of whatever the key already holds -- so an existing
    PYTHONPATH from os.environ, default.yml or a project YAML is kept.
    """
    resolved = {p.split("-")[0] for p in rez_pkgs}
    code = (software.get("code") or "").lower().replace(" ", "")
    dcc_root = config.DCC_SOURCE_ROOT
    out = {}

    if config.REZ_DCC_PACKAGE and config.REZ_DCC_PACKAGE in resolved:
        log.info("%s is resolved by rez — using the released package",
                 config.REZ_DCC_PACKAGE)
        return out

    roots = [dcc_root]
    if not (config.REZ_CONTEXT_PACKAGE and
            config.REZ_CONTEXT_PACKAGE in resolved):
        roots.append(config.CONTEXT_SOURCE_ROOT)
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

    log.info("%s not in the rez resolve — falling back to the source tree",
             config.REZ_DCC_PACKAGE)
    out["PYTHONPATH+"] = os.pathsep.join(roots)
    return out


def _keep_tools_paths_through_rez(cmd, env, tools):
    """Stop `rez env` from dropping the fallback paths _tools_paths() set.

    rez resets any variable a resolved package writes to, so maya's own
    PYTHONPATH.prepend wipes what ShotDeck put there before the DCC ever
    starts -- which is why the source tree was missing from Maya's PYTHONPATH
    even when the launch environment held it. Variables named in
    parent_variables are inherited instead of reset; REZ_PARENT_VARIABLES is
    the environment override for that setting.

    Only the variables ShotDeck actually filled are asked for, and only when
    the fallback is in play: with shotdeck_dcc in the resolve `tools` is empty
    and rez's environment is left exactly as it is today. Nothing here forces a
    rez launch either -- it edits the environment of a command that is already
    `rez env`.
    """
    wanted = [k[:-1] for k in tools if k.endswith("+")]
    if not wanted:
        return
    if os.path.basename(cmd[0]) != os.path.basename(config.REZ_EXECUTABLE):
        return

    keep = [v for v in env.get("REZ_PARENT_VARIABLES", "").split(",") if v]
    for name in wanted:
        if name not in keep:
            keep.append(name)
    env["REZ_PARENT_VARIABLES"] = ",".join(keep)


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
