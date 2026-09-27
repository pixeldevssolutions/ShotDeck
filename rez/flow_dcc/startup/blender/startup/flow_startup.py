"""Blender startup hook, reached through BLENDER_USER_SCRIPTS.

Blender imports every .py under <scripts>/startup/ once the UI exists, which
is exactly when the menu can be registered.

Failure is printed, never raised: an artist should get Blender without the
menu rather than no Blender at all.
"""

import traceback

try:
    import flow_dcc
    flow_dcc.install()
except Exception:
    traceback.print_exc()
