"""Houdini startup hook, reached through HOUDINI_PATH.

Houdini runs 123.py when it starts on an empty scene and 456.py when it starts
by opening one, so a launch is one or the other. Both call install(), which
replaces any menu it finds rather than adding a second.

Failure is printed, never raised: an artist should get Houdini without the
menu rather than no Houdini at all.
"""

import traceback

try:
    import flow_dcc
    flow_dcc.install()
except Exception:
    traceback.print_exc()
