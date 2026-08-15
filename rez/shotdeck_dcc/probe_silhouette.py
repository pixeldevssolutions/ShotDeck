#!/usr/bin/env python
"""Report what this Silhouette build actually exposes to Python.

Run it inside Silhouette (script console, or whatever this version calls it):

    exec(open("/path/to/shotdeck_dcc/probe_silhouette.py").read())

or from the shell to at least see the interpreter and the environment:

    rez env silhouette shotdeck_dcc -- python $SHOTDECK_DCC_ROOT/probe_silhouette.py

Nothing here imports ShotDeck code or assumes an API -- it only looks. Paste
the output into the ticket and the adapter gets wired from facts.
"""

import os
import sys

CANDIDATE_MODULES = ["fx", "silhouette", "sfx", "hy"]
INTERESTING = ("menu", "action", "save", "project", "session", "window",
               "command", "script", "ui")
PATH_VARS = ("SFX_SCRIPT_PATH", "SILHOUETTE_SCRIPT_PATH", "SFX_PATH",
             "SILHOUETTE_PATH", "PYTHONPATH", "SHOTDECK_DCC_ROOT")


def main():
    print("=" * 70)
    print("Silhouette probe")
    print("=" * 70)
    print("python      {0}".format(sys.version.replace("\n", " ")))
    print("executable  {0}".format(sys.executable))
    print("argv        {0}".format(sys.argv))

    print("\n-- host modules " + "-" * 54)
    found = []
    for name in CANDIDATE_MODULES:
        try:
            module = __import__(name)
        except ImportError as e:
            print("{0:<12} not importable ({1})".format(name, e))
            continue
        found.append((name, module))
        print("{0:<12} {1}".format(name, getattr(module, "__file__", "builtin")))
        for attr in ("__version__", "version", "VERSION"):
            if hasattr(module, attr):
                print("{0:<12}   {1} = {2!r}".format(
                    "", attr, getattr(module, attr)))

    for name, module in found:
        print("\n-- {0}: attributes mentioning {1} {2}".format(
            name, "/".join(INTERESTING), "-" * 10))
        names = sorted(a for a in dir(module)
                       if any(word in a.lower() for word in INTERESTING))
        if not names:
            print("  (none)")
        for attr in names:
            value = getattr(module, attr, None)
            print("  {0:<28} {1}".format(attr, type(value).__name__))

    print("\n-- script search paths " + "-" * 47)
    for var in PATH_VARS:
        print("{0:<26} {1}".format(var, os.environ.get(var, "(unset)")))

    print("\n-- ShotDeck context " + "-" * 50)
    shotdeck = {k: v for k, v in os.environ.items() if k.startswith("SHOTDECK_")}
    if not shotdeck:
        print("  no SHOTDECK_* variables — this was not a ShotDeck launch")
    for key in sorted(shotdeck):
        print("  {0:<30} {1}".format(key, shotdeck[key]))

    print("\n-- import shotdeck_dcc " + "-" * 47)
    try:
        import shotdeck_dcc
        print("  ok: {0} ({1})".format(shotdeck_dcc.__version__,
                                       shotdeck_dcc.__file__))
    except ImportError as e:
        print("  FAILED: {0}".format(e))
        print("  PYTHONPATH is not reaching this interpreter — that is the "
              "first thing to fix.")


if __name__ == "__main__":
    main()
else:
    main()          # exec()'d into a script console: run on the way in
