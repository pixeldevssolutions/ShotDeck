"""Nuke startup hook, reached through NUKE_PATH from the flow_dcc package.

init.py runs in every Nuke session including -t and -x, so it deliberately does
no GUI work: it only proves the package is importable and says so in the launch
log, which is where a broken deploy shows up first. The menu is menu.py's job.
"""

import traceback

try:
    import flow_dcc
    print("Flow: flow_dcc %s available (%s)"
          % (flow_dcc.__version__, flow_dcc.__file__))
except Exception:
    traceback.print_exc()
