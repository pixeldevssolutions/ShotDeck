import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

import applog
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
    try:
        sg = SGClient()
    except Exception as e:
        # Most often a missing SG_SCRIPT_KEY; a dialog beats a traceback into
        # a terminal the artist never sees.
        log.error("could not connect to ShotGrid: %s", e)
        QMessageBox.critical(None, "ShotDeck", str(e))
        return 1

    win = MainWindow(sg)
    if args.console:
        win.show_console()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
