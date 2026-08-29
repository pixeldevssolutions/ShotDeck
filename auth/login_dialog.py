"""Username/password dialog for the LDAP bind fallback.

Only reached when the system-login trust path could not authorize the artist.
The password is read straight out of the field into the bind call and is never
stored on the dialog, echoed to the log, or offered a "remember me" checkbox.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ui import theme


class LoginDialog(QDialog):
    def __init__(self, cfg, message="", parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Flow - Sign in")
        self.setMinimumWidth(380)
        self.setStyleSheet(theme.STYLE)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        title = QLabel(f"Sign in to {cfg.domain or 'the studio domain'}")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        hint = QLabel(f"Use your workstation login. Members of "
                      f"{cfg.required_group or 'the authorized group'} only.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        root.addWidget(hint)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText(cfg.down_level("username"))
        root.addWidget(self._row("Username", self.user_edit))

        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setPlaceholderText("Password")
        root.addWidget(self._row("Password", self.pass_edit))

        self.error_lbl = QLabel(message)
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setObjectName("error")
        self.error_lbl.setVisible(bool(message))
        root.addWidget(self.error_lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Sign in")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.ok_btn = buttons.button(QDialogButtonBox.Ok)

        self.user_edit.textChanged.connect(self._sync)
        self.pass_edit.textChanged.connect(self._sync)
        self.pass_edit.returnPressed.connect(self._accept)
        self._sync()

    def _row(self, label, widget):
        row = QWidget()
        box = QVBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        cap = QLabel(label)
        cap.setObjectName("fieldLabel")
        box.addWidget(cap)
        box.addWidget(widget)
        return row

    def _sync(self):
        self.ok_btn.setEnabled(bool(self.user_edit.text().strip())
                               and bool(self.pass_edit.text()))

    def _accept(self):
        if self.ok_btn.isEnabled():
            self.accept()

    def credentials(self):
        """(username, password) as typed. Read once, then discard the dialog."""
        return self.user_edit.text().strip(), self.pass_edit.text()


def prompt(cfg, message="", parent=None):
    """Show the dialog. Returns (username, password), or None if cancelled.

    This is the callable ad_auth.authenticate() expects for its prompt
    argument. The dialog is deleted immediately so the password text does not
    outlive the call any longer than Qt's own buffers force.
    """
    dlg = LoginDialog(cfg, message=message, parent=parent)
    try:
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.credentials()
    finally:
        dlg.pass_edit.clear()
        dlg.deleteLater()
