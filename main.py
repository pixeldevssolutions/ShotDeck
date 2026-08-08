import sys

from PySide6.QtWidgets import QApplication

from sg_client import SGClient
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    sg = SGClient()
    win = MainWindow(sg)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
