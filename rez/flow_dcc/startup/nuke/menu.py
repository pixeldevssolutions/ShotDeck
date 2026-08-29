"""Nuke GUI startup hook: builds the Flow menu.

Nuke runs menu.py from every NUKE_PATH entry in GUI sessions only, which is
exactly when a menu makes sense. Failure is printed, never raised -- a comp
artist should get Nuke without the menu rather than no Nuke at all.
"""

import traceback

try:
    import flow_dcc
    flow_dcc.install()
except Exception:
    traceback.print_exc()
