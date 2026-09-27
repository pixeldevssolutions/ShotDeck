"""Client delivery: pick approved shots, preview, deliver.

Drawing only. What gets offered, what counts as a problem and how files move
all live in package_service.
"""

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
)

import applog
import delivery_core
import package_service
from . import jobs

log = applog.get()


class PackageDialog(QDialog):
    COLS = ["", "Sequence", "Shot", "Approved version", "Approved"]

    def __init__(self, sg, project, parent=None):
        super().__init__(parent)
        self.sg = sg
        self.project = project
        self.cfg = None
        self.cfg_path = ""
        self._versions = []
        self._jobs = set()
        self.pool = QThreadPool.globalInstance()

        self.setWindowTitle(f"Client delivery — {project['name']}")
        self.resize(820, 620)

        lay = QVBoxLayout(self)
        heading = QLabel("Client delivery")
        heading.setObjectName("headerTitle")
        lay.addWidget(heading)

        row = QHBoxLayout()
        self.cfg_lbl = QLabel("Looking for a delivery config…")
        self.cfg_lbl.setObjectName("tileSub")
        self.cfg_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.cfg_lbl, 1)
        browse = QPushButton("Choose config…")
        browse.setObjectName("consoleBtn")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        lay.addLayout(row)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch)
        lay.addWidget(self.table, 2)

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setPlaceholderText(
            "Preview checks the package without copying anything. "
            "Deliver runs the same check first.")
        lay.addWidget(self.out, 1)

        buttons = QHBoxLayout()
        self.status = QLabel("Loading approved versions…")
        self.status.setObjectName("tileSub")
        buttons.addWidget(self.status, 1)
        close = QPushButton("Close")
        close.setObjectName("consoleBtn")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setObjectName("consoleBtn")
        self.preview_btn.clicked.connect(lambda: self._go(deliver=False))
        buttons.addWidget(self.preview_btn)
        self.deliver_btn = QPushButton("Deliver")
        self.deliver_btn.setObjectName("termBtn")
        self.deliver_btn.clicked.connect(lambda: self._go(deliver=True))
        buttons.addWidget(self.deliver_btn)
        lay.addLayout(buttons)
        self._set_busy(True)

        cfg, path = delivery_core.find_config(
            package_service.project_code(project),
            log=lambda m, lvl="info": log.info(m))
        self._set_config(cfg, path)
        self._run(self.sg.approved_shot_versions, self._on_versions, project)

    # -- data ---------------------------------------------------------------

    def _run(self, fn, on_result, *args):
        jobs.run(self._jobs, fn, on_result, *args, pool=self.pool,
                 on_error=self._on_error)

    def _on_error(self, msg):
        log.error("delivery: %s", msg)
        self.status.setText("Failed — see below")
        self.out.appendPlainText(f"ERROR: {msg}")
        self._set_busy(False)

    def _set_config(self, cfg, path):
        self.cfg, self.cfg_path = cfg, path
        self.cfg_lbl.setText(
            f"Config: {path}  ({cfg.get('client', '?')})" if cfg else
            "No delivery config found for this project — choose one.")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Delivery config", self.cfg_path,
            "Delivery config (*.yaml *.yml *.json)")
        if not path:
            return
        try:
            self._set_config(delivery_core.load_config(path), path)
        except Exception as e:
            self.out.appendPlainText(f"Could not read {path}: {e}")

    def _on_versions(self, versions):
        self._versions = versions
        self.table.setRowCount(len(versions))
        for r, v in enumerate(versions):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Unchecked)
            self.table.setItem(r, 0, check)
            seq = (v.get("entity.Shot.sg_sequence") or {}).get("name") or ""
            when = v.get("created_at")
            for c, text in enumerate([
                    seq, v["entity"].get("name") or "", v.get("code") or "",
                    f"{when:%d %b %Y}" if hasattr(when, "strftime")
                    else str(when or "")], start=1):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.status.setText(
            f"{len(versions)} shot(s) with an approved version" if versions
            else "No shot in this project has an approved version")
        self._set_busy(False)

    def checked(self):
        return [self._versions[r] for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.Checked]

    # -- preview / deliver ----------------------------------------------------

    def _go(self, deliver):
        versions = self.checked()
        if not versions:
            self.status.setText("Tick at least one shot")
            return
        if not self.cfg:
            self.status.setText("Choose a delivery config first")
            return
        self.out.clear()
        self._set_busy(True)
        self.status.setText(
            f"{'Delivering' if deliver else 'Checking'} {len(versions)} "
            f"shot(s)… large plates take a while")
        cfg, project, sg = self.cfg, self.project, self.sg

        def work():
            outcomes = []
            for v in versions:
                try:
                    shot = package_service.shot_delivery(project, v)
                except package_service.DeliveryError as e:
                    outcomes.append((v.get("code"), None, [str(e)]))
                    continue
                o = (package_service.deliver(cfg, shot, sg) if deliver
                     else package_service.preview(cfg, shot))
                outcomes.append((shot.label, o, o.problems))
            return outcomes

        self._run(work, lambda res: self._show(res, deliver))

    def _show(self, outcomes, deliver):
        good = 0
        for label, o, bad in outcomes:
            files = len(o.result.entries) if o and o.result else 0
            size = sum(e.size for e in o.result.entries) if files else 0
            if bad:
                self.out.appendPlainText(f"✗ {label}")
                for p in bad:
                    self.out.appendPlainText(f"    {p}")
            else:
                good += 1
                done = "delivered to " + str(o.shot.output_root) if deliver \
                    else "ready"
                self.out.appendPlainText(
                    f"✓ {label}: {files} files, {size / 1e9:.2f} GB — {done}")
            if o:
                for rule, why in o.result.skipped:
                    self.out.appendPlainText(f"    note: {rule} — {why}")
        verb = "delivered" if deliver else "ready"
        self.status.setText(f"{good} of {len(outcomes)} {verb}")
        self._set_busy(False)

    def _set_busy(self, busy):
        for b in (self.preview_btn, self.deliver_btn):
            b.setEnabled(not busy)
