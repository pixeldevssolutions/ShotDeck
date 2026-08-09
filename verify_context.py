"""Check that a launched app really receives the ShotGrid context.

Two ways to use it:

    # Run a dump through the real launch path, inside rez
    python verify_context.py --project-id 1213 --task-id 7631 --package pureref

    # Or inspect an app that is already running
    python verify_context.py --pid 961346

The first proves the whole chain: SG query -> context file -> env merge ->
rez env -> process. The second proves it for the actual DCC an artist is sitting
in front of, which is the one that really matters.
"""

import argparse
import json
import os
import sys
import time

import applog
import config
import rez_scan

# sg_client and launcher are imported inside launch_probe(), so that --pid
# works on a box without shotgun_api3 installed.

# What a launched app must have to be able to publish.
REQUIRED = [
    "SHOTDECK_CONTEXT_FILE",
    "SHOTDECK_SITE",
    "SHOTDECK_USER_EMAIL",
    "SHOTDECK_PROJECT_ID",
    "SHOTDECK_TASK_ID",
    "SHOTDECK_ENTITY_TYPE",
    "SHOTDECK_ENTITY_ID",
]
# Nice to have, but a launch without a task legitimately leaves these empty.
OPTIONAL = [
    "SHOTDECK_PROJECT_CODE",
    "SHOTDECK_PROJECT_NAME",
    "SHOTDECK_TASK_NAME",
    "SHOTDECK_STEP",
    "SHOTDECK_ENTITY_NAME",
    "SHOTDECK_SOFTWARE",
    "SHOTDECK_SOFTWARE_VERSION",
]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pid", type=int,
                   help="inspect a running process instead of launching one")
    p.add_argument("--project-id", type=int)
    p.add_argument("--task-id", type=int)
    p.add_argument("--package", help="rez package to launch inside, e.g. pureref")
    p.add_argument("--version", help="package version; newest if omitted")
    p.add_argument("--wait", type=float, default=6.0,
                   help="seconds to wait for the dump to appear (default 6)")
    args = p.parse_args()

    applog.setup(verbose=True)

    if args.pid:
        return inspect_pid(args.pid)
    if not (args.project_id and args.task_id):
        p.error("need --pid, or both --project-id and --task-id")
    return launch_probe(args)


# -- inspect a running process --------------------------------------------

def inspect_pid(pid):
    environ_path = f"/proc/{pid}/environ"
    if not os.path.exists(environ_path):
        print(f"No such process, or not Linux: {environ_path}")
        return 2
    try:
        with open(environ_path, "rb") as f:
            raw = f.read()
    except PermissionError:
        print(f"Cannot read {environ_path} — it must be your own process.")
        return 2

    env = {}
    for item in raw.split(b"\0"):
        if b"=" in item:
            k, v = item.split(b"=", 1)
            env[k.decode(errors="replace")] = v.decode(errors="replace")

    print(f"\nProcess {pid}: {_cmdline(pid)}\n")
    return report(env)


def _cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return " ".join(f.read().decode(errors="replace").split("\0")).strip()
    except OSError:
        return "?"


# -- launch a dump through the real path ----------------------------------

def launch_probe(args):
    import launcher
    from sg_client import SGClient

    sg = SGClient()
    sg.resolve_owner(config.current_user_email(os.environ.get("USER", "")))

    project = sg.sg.find_one("Project", [["id", "is", args.project_id]],
                             config.PROJECT_FIELDS)
    if not project:
        print(f"No project with id {args.project_id}")
        return 2
    task = sg.sg.find_one("Task", [["id", "is", args.task_id]],
                          config.TASK_FIELDS)
    if not task:
        print(f"No task with id {args.task_id}")
        return 2

    package = args.package
    version = args.version
    if package and not version:
        for name, versions in rez_scan.scan():
            if name == package:
                version = versions[0]
                break

    # Same code path as a real launch -- only the command differs. `env` here
    # is the coreutils binary, which prints the environment it was handed.
    software = {
        "code": package or "context-probe",
        "version": version or "",
        "linux_path": "env",
        "linux_args": "",
    }
    if package:
        software[config.SOFTWARE_REZ_FIELD] = rez_scan.request(package, version)

    print(f"\nProbing: project {project['name']}, task {task['id']} "
          f"({task.get('content')})"
          f"{', inside rez ' + rez_scan.request(package, version) if package else ''}\n")

    pid, log_path = launcher.launch(
        project, software,
        login=os.environ.get("USER"),
        email=config.current_user_email(os.environ.get("USER", "")),
        task=task)

    env = _read_dump(log_path, args.wait)
    if env is None:
        print(f"Nothing was written to {log_path} within {args.wait}s.")
        print("Check the log by hand — the resolve may have failed.")
        return 2

    code = report(env)
    print(f"\nFull output: {log_path}")
    return code


def _read_dump(log_path, wait):
    """Wait for the child to write its environment, then parse it."""
    marker = "process output below"
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            with open(log_path, "r", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        if marker in text:
            body = text.split(marker, 1)[1]
            env = {}
            for line in body.splitlines():
                if "=" in line and not line.startswith("-"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v
            if env:
                return env
        time.sleep(0.3)
    return None


# -- reporting -------------------------------------------------------------

def report(env):
    """Print what arrived and whether it is usable. Returns an exit code."""
    failures = []

    print("Required")
    for key in REQUIRED:
        value = env.get(key)
        ok = bool(value)
        # An app launched with no task selected has these set but empty, which
        # is legitimate -- flag it as a warning rather than a failure.
        if key in ("SHOTDECK_TASK_ID", "SHOTDECK_ENTITY_TYPE",
                   "SHOTDECK_ENTITY_ID") and key in env and not value:
            print(f"  ~ {key:<28} (empty — launched without a task)")
            continue
        print(f"  {'OK' if ok else 'MISSING':<2} {key:<28} {value or ''}")
        if not ok:
            failures.append(key)

    print("\nOptional")
    for key in OPTIONAL:
        value = env.get(key, "")
        print(f"  {'  ' if value else '~ '} {key:<28} {value}")

    rez_used = env.get("REZ_USED_RESOLVE") or env.get("REZ_USED_REQUEST")
    print("\nrez")
    if rez_used:
        print(f"   OK  resolved: {rez_used}")
    else:
        print("   ~   no REZ_USED_* — this did not run inside a rez context")

    # The context file is the thing publish tools actually read.
    print("\nContext file")
    path = env.get("SHOTDECK_CONTEXT_FILE")
    if not path:
        print("   MISSING  SHOTDECK_CONTEXT_FILE was not set")
        failures.append("SHOTDECK_CONTEXT_FILE")
    elif not os.path.isfile(path):
        print(f"   MISSING  {path} does not exist")
        failures.append("context file")
    else:
        try:
            with open(path) as f:
                data = json.load(f)
            task = data.get("task") or {}
            print(f"   OK  {path}")
            print(f"       project {data['project']['name']} "
                  f"(code {data['project']['code'] or '—'})")
            print(f"       task    {task.get('name') or '(none)'} "
                  f"on {task.get('entity_name') or '—'} "
                  f"[{task.get('entity_type') or '—'} {task.get('entity_id') or '—'}]")
            print(f"       user    {data['user']['email']}")
        except (ValueError, KeyError, OSError) as e:
            print(f"   BAD  {path}: {e}")
            failures.append("context file")

    print("\nshotdeck_context package")
    if rez_scan.is_available(config.REZ_CONTEXT_PACKAGE):
        print("   OK  released — in-DCC tools can import it")
    else:
        print("   ~   not built yet, so tools must read the SHOTDECK_* vars")
        print("       build with: cd rez/shotdeck_context && rez build -ic")

    print()
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("PASS — the app receives a usable context.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
