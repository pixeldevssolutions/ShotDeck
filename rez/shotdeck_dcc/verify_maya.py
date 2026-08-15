#!/usr/bin/env python
"""Check, from inside Maya, that the ShotDeck integration actually loaded.

Paste into Maya's Script Editor (Python tab) and run:

    exec(open("/software/packages/tools/shotdeck_dcc/1.0.0/verify_maya.py").read())

or, when the package is resolved, without knowing the version:

    import os
    exec(open(os.environ["SHOTDECK_DCC_ROOT"] + "/verify_maya.py").read())

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


@check("shotdeck_dcc is importable")
def _importable():
    try:
        import shotdeck_dcc
    except ImportError as e:
        return _fail(
            "{0}\n     PYTHONPATH is not reaching Maya. Was Maya launched "
            "from ShotDeck, or with `rez env maya-<ver> shotdeck_dcc -- maya`? "
            "Check that shotdeck_dcc is built: cd rez/shotdeck_dcc && "
            "rez build -ic".format(e))
    return _pass("{0} ({1})".format(shotdeck_dcc.__version__,
                                    shotdeck_dcc.__file__))


@check("the launch context arrived")
def _context():
    import shotdeck_dcc

    ctx = shotdeck_dcc.context.get()
    missing = ctx.missing()
    if missing:
        return _fail(
            "missing {0}\n     Maya was started outside ShotDeck, or with no "
            "task selected. Pick a task in ShotDeck and relaunch."
            .format(", ".join(missing)))
    return _pass("{0} / {1} / {2} (step {3})".format(
        ctx.project_name, ctx.entity_name, ctx.task_name, ctx.step))


@check("this session resolved to the maya adapter")
def _adapter():
    import shotdeck_dcc

    name = shotdeck_dcc.software()
    if name != "maya":
        return _fail(
            "SHOTDECK_SOFTWARE={0!r} resolves to {1!r}, not 'maya'. The menu "
            "is built for whatever that names, so nothing Maya-shaped loaded. "
            "Add the code to shotdeck_dcc.ALIASES if this is Maya under "
            "another name.".format(os.environ.get("SHOTDECK_SOFTWARE"), name))
    return _pass("adapter {0}".format(shotdeck_dcc.adapter().__file__))


@check("userSetup.py ran")
def _startup():
    if "userSetup" in sys.modules:
        return _pass(getattr(sys.modules["userSetup"], "__file__", "?"))
    return _fail(
        "Maya never imported a userSetup.py. The startup folder is not on "
        "PYTHONPATH -- check that package.py's `if \"maya\" in resolve:` block "
        "ran, i.e. that maya really is in this rez resolve.")


@check("the ShotDeck menu exists")
def _menu():
    import maya.cmds as cmds

    from shotdeck_dcc.adapters import maya as adapter

    if cmds.about(batch=True):
        return _fail("this is a batch session (mayapy), which has no menu bar")
    if not cmds.menu(adapter.MENU_OBJECT, exists=True):
        return _fail(
            "no menu named {0!r}. Build it by hand to see the error: "
            "import shotdeck_dcc; shotdeck_dcc.install()"
            .format(adapter.MENU_OBJECT))
    return _pass(cmds.menu(adapter.MENU_OBJECT, query=True, label=True))


@check("the menu has every action")
def _items():
    import maya.cmds as cmds

    from shotdeck_dcc.adapters import ACTIONS
    from shotdeck_dcc.adapters import maya as adapter

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
    import shotdeck_dcc

    target = shotdeck_dcc.publish.describe_target()
    if not target.startswith("/"):
        return _fail(target)        # describe_target explains why, in words
    if os.path.exists(target):
        return _fail("{0}\n     already exists, so the version scan is wrong"
                     .format(target))
    return _pass(target)


def main():
    print("=" * 70)
    print("ShotDeck integration check -- Maya")
    print("=" * 70)

    failed = 0
    for label, func in CHECKS:
        try:
            ok, detail = func()
        except Exception as e:
            ok, detail = False, "{0}: {1}".format(type(e).__name__, e)
        print("{0}  {1}".format("PASS" if ok else "FAIL", label))
        if detail:
            print("      {0}".format(detail))
        if not ok:
            failed += 1
            if label == CHECKS[0][0]:
                print("\nStopping: nothing else can pass while the import fails.")
                break

    print("-" * 70)
    print("{0} of {1} checks passed".format(len(CHECKS) - failed, len(CHECKS)))
    return failed


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
else:
    main()          # exec()'d into the Script Editor: run on the way in
