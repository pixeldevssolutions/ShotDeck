name = "shotdeck_dcc"

version = "1.0.0"

description = \
    "ShotDeck's in-DCC tools: the Python package the adapters live in, plus " \
    "the per-DCC startup hooks that load them automatically. Resolving this " \
    "package is the whole install -- artists never copy a userSetup.py or " \
    "edit a personal PYTHONPATH."

authors = ["pipeline"]

# shotdeck_context reads the launch context; this package is the tooling on top
# of it. Requiring it means one request (shotdeck_dcc) pulls in both.
requires = [
    "shotdeck_context",
]

variants = [
    ["platform-linux", "arch-x86_64"],
]

build_command = "python {root}/REZ_INSTALLER.py"


def commands():
    # `import shotdeck_dcc` inside any DCC.
    env.PYTHONPATH.prepend("{root}/python")

    # Where the adapters look for their own startup trees, and what the probe
    # scripts report on.
    env.SHOTDECK_DCC_ROOT = "{root}"

    # The startup hooks are wired per DCC, and only for the DCC that is
    # actually being launched -- Maya's userSetup.py must never end up on
    # Nuke's PYTHONPATH, and NUKE_PATH means nothing to Maya.
    #
    # Two signals, because either one alone has a hole: the resolve misses a
    # studio that wraps the DCC under another package name, and the context
    # variable is absent when someone runs `rez env maya shotdeck_dcc` by
    # hand outside ShotDeck. Matching either is what makes the menu appear
    # without anyone typing a Python command.
    software = str(env.SHOTDECK_SOFTWARE).lower() \
        if "SHOTDECK_SOFTWARE" in env else ""

    if "maya" in resolve or software.startswith("maya"):
        # Maya executes any userSetup.py it finds on PYTHONPATH at startup.
        env.PYTHONPATH.prepend("{root}/startup/maya")

    if "nuke" in resolve or software.startswith("nuke"):
        # Nuke scans every NUKE_PATH entry for init.py (always) and menu.py
        # (GUI sessions only).
        env.NUKE_PATH.prepend("{root}/startup/nuke")

    # Silhouette is deliberately not wired here yet: its startup mechanism has
    # not been confirmed on the 5and8 farm, and guessing an environment
    # variable would fail silently rather than loudly. Run
    #   rez env silhouette shotdeck_dcc -- python {root}/probe_silhouette.py
    # inside Silhouette's interpreter and wire the result in. The adapter and
    # the menu code are already written and work once something calls
    # shotdeck_dcc.install().
