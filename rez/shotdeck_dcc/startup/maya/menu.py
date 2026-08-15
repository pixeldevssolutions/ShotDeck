"""Maya menu construction, deferred from userSetup.py.

Split from userSetup.py to match Nuke's init.py/menu.py shape: userSetup.py is
the entry point Maya insists on, this is the part that builds the menu. Keep
it importable without side effects -- userSetup.py calls install() once the
main window exists.
"""

import traceback


def install():
    """Build the ShotDeck menu. Never raises -- a menu is not worth a crash."""
    try:
        import shotdeck_dcc
        return shotdeck_dcc.install()
    except Exception:
        traceback.print_exc()
        return False
