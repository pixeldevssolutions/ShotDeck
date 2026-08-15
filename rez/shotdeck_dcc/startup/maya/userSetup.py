"""Maya startup hook, reached through PYTHONPATH from the shotdeck_dcc package.

Maya executes every userSetup.py it finds on PYTHONPATH once the GUI is up.
package.py only puts this folder on PYTHONPATH when maya is in the resolve, so
it never loads inside another DCC.

The menu build is deferred: at the time userSetup.py runs, $gMainWindow does
not exist yet and cmds.menu(parent=...) fails.
"""

import traceback


def _install():
    try:
        import shotdeck_dcc
        shotdeck_dcc.install()
    except Exception:
        # Never let a menu take Maya down with it -- print and carry on.
        traceback.print_exc()


try:
    import maya.utils
    maya.utils.executeDeferred(_install)
except Exception:
    traceback.print_exc()
