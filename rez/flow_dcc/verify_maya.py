#!/usr/bin/env python
"""Check, from inside Maya, that the Flow integration actually loaded.

Paste into Maya's Script Editor (Python tab) and run:

    import os
    root = os.environ.get("FLOW_DCC_ROOT",
                          "/software/pipeline/Flow/rez/flow_dcc")
    exec(open(root + "/verify_maya.py").read())

FLOW_DCC_ROOT is set by the rez package, so it is unset exactly when the
package is not in the resolve -- which is itself the answer. The fallback above
reads the checker straight out of the source tree so it still runs and says so.

Every check prints PASS or FAIL with what to do about it. A FAIL on the first
check makes the rest meaningless, so it stops there. Reads nothing and writes
nothing -- safe to run in the middle of a shot.
"""

import os
import sys

CHECKS = []


def check(label):
    def wrap(func):
        CHECKS.append((label, func))
        return func
    return wrap


def _fail(message):
    return False, message


def _pass(message=""):
    return True, message


@check("flow_dcc is importable")
def _importable():
    try:
        import flow_dcc
    except ImportError as e:
        if not os.environ.get("FLOW_DCC_ROOT"):
            return _fail(
                "{0}\n     FLOW_DCC_ROOT is unset too, so flow_dcc was "
                "not in this rez resolve at all. Usually that means it has "
                "never been built: cd /software/pipeline/Flow/rez/"
                "flow_dcc && rez build -ic, then relaunch. Flow skips "
                "injecting a package that is not released and logs a warning "
                "in the session log.".format(e))
        return _fail(
            "{0}\n     FLOW_DCC_ROOT is set ({1}), so the package resolved "
            "but its python/ folder is not on Maya's PYTHONPATH. Check the "
            "PYTHONPATH.prepend in package.py against what the install "
            "actually contains.".format(e, os.environ["FLOW_DCC_ROOT"]))
    return _pass("{0} ({1})".format(flow_dcc.__version__,
                                    flow_dcc.__file__))


@check("the launch context arrived")
def _context():
    import flow_dcc

    ctx = flow_dcc.context.get()
    missing = ctx.missing()
    if missing:
        return _fail(
            "missing {0}\n     Maya was started outside Flow, or with no "
            "task selected. Pick a task in Flow and relaunch."
            .format(", ".join(missing)))
    return _pass("{0} / {1} / {2} (step {3})".format(
        ctx.project_name, ctx.entity_name, ctx.task_name, ctx.step))


@check("this session resolved to the maya adapter")
def _adapter():
    import flow_dcc

    name = flow_dcc.software()
    if name != "maya":
        return _fail(
            "FLOW_SOFTWARE={0!r} resolves to {1!r}, not 'maya'. The menu "
            "is built for whatever that names, so nothing Maya-shaped loaded. "
            "Add the code to flow_dcc.ALIASES if this is Maya under "
            "another name.".format(os.environ.get("FLOW_SOFTWARE"), name))
    return _pass("adapter {0}".format(flow_dcc.adapter().__file__))


@check("userSetup.py ran")
def _startup():
    if "userSetup" in sys.modules:
        return _pass(getattr(sys.modules["userSetup"], "__file__", "?"))
    return _fail(
        "Maya never imported a userSetup.py. The startup folder is not on "
        "PYTHONPATH -- check that package.py's `if \"maya\" in resolve:` block "
        "ran, i.e. that maya really is in this rez resolve.")


@check("the Flow menu exists")
def _menu():
    import maya.cmds as cmds

    from flow_dcc.adapters import maya as adapter

    if cmds.about(batch=True):
        return _fail("this is a batch session (mayapy), which has no menu bar")
    if not cmds.menu(adapter.MENU_OBJECT, exists=True):
        return _fail(
            "no menu named {0!r}. Build it by hand to see the error: "
            "import flow_dcc; flow_dcc.install()"
            .format(adapter.MENU_OBJECT))
    return _pass(cmds.menu(adapter.MENU_OBJECT, query=True, label=True))


@check("the menu has every action")
def _items():
    import maya.cmds as cmds

    from flow_dcc.adapters import ACTIONS
    from flow_dcc.adapters import maya as adapter

    expected = [label for label, _ in ACTIONS if label]
    items = cmds.menu(adapter.MENU_OBJECT, query=True, itemArray=True) or []
    found = [cmds.menuItem(item, query=True, label=True) for item in items
             if not cmds.menuItem(item, query=True, divider=True)]

    missing = [label for label in expected if label not in found]
    if missing:
        return _fail("missing {0} (found {1})".format(missing, found))
    return _pass(", ".join(found))


@check("a save would land in the right place")
def _target():
    import flow_dcc

    target = flow_dcc.publish.describe_target()
    if not target.startswith("/"):
        return _fail(target)        # describe_target explains why, in words
    if os.path.exists(target):
        return _fail("{0}\n     already exists, so the version scan is wrong"
                     .format(target))
    return _pass(target)


def main():
    print("=" * 70)
    print("Flow integration check -- Maya")
    print("=" * 70)

    passed = failed = 0
    for label, func in CHECKS:
        try:
            ok, detail = func()
        except Exception as e:
            ok, detail = False, "{0}: {1}".format(type(e).__name__, e)
        print("{0}  {1}".format("PASS" if ok else "FAIL", label))
        if detail:
            print("      {0}".format(detail))
        if ok:
            passed += 1
            continue

        failed += 1
        if label == CHECKS[0][0]:
            print("\nStopping: nothing else can pass while the import fails.")
            break

    print("-" * 70)
    skipped = len(CHECKS) - passed - failed
    summary = "{0} of {1} checks passed".format(passed, len(CHECKS))
    if skipped:
        summary += ", {0} not run".format(skipped)
    print(summary)
    return failed


# Maya's Script Editor execs with __name__ == "__main__" and no __file__, so
# __name__ alone cannot tell a real command-line run from a paste -- and
# sys.exit() inside the Script Editor surfaces as "# Error: SystemExit".
_AS_SCRIPT = (__name__ == "__main__"
              and globals().get("__file__", "").endswith("verify_maya.py"))

_failed = main()
if _AS_SCRIPT:
    sys.exit(1 if _failed else 0)
