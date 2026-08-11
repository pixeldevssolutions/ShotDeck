import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

import applog
import auth
from auth import login_dialog
from sg_client import SGClient
from ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="ShotDeck")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log every command and environment detail")
    parser.add_argument("--console", action="store_true",
                        help="open with the Terminal panel already showing")
    args = parser.parse_args()

    log = applog.setup(verbose=args.verbose)
    log.info("ShotDeck starting")

    app = QApplication(sys.argv)

    # Authenticate before anything talks to ShotGrid or launches a DCC. On a
    # domain-joined box this is silent; otherwise it prompts. Fail closed.
    result = auth.authenticate(prompt=login_dialog.prompt)
    if not result.authorized:
        log.error("authentication failed: %s", result.reason)
        QMessageBox.critical(None, "ShotDeck",
                             result.reason or "You are not authorized to use "
                                              "ShotDeck.")
        return 1
    log.info("signed in as %s (%s)", result.login, result.method)

    try:
        sg = SGClient()
    except Exception as e:
        # Most often a missing SG_SCRIPT_KEY; a dialog beats a traceback into
        # a terminal the artist never sees.
        log.error("could not connect to ShotGrid: %s", e)
        QMessageBox.critical(None, "ShotDeck", str(e))
        return 1

    win = MainWindow(sg, login=result.login)
    if args.console:
        win.show_console()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
