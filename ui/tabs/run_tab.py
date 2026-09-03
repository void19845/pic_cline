from __future__ import annotations
"""ui.tabs.run_tab — configuration + run + live progress."""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from organizer.reporting import RunSummary
from ui.prefs import Prefs
from ui.widgets.path_picker import PathPicker


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("background-color: #2e2e38; max-height: 1px; border: none;")
    return line


class RunTab(QWidget):
    """
    Emits run_requested(dict) with everything process_vault() needs when
    the user clicks Run — MainWindow owns the PipelineController and
    wires this tab's signal to controller.start(**kwargs).

    RunTab never imports organizer/ or core/ beyond RunSummary (a plain
    dataclass, Qt-free) for type hints — it only knows Qt and Prefs.
    """
    run_requested = pyqtSignal(dict)
    stop_requested = pyqtSignal()

    def __init__(self, prefs: Prefs, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.prefs = prefs
        self._build()
        self._load_prefs()

    # ── UI construction ──────────────────────────────────────────────────
    def _build(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Run")
        title.setObjectName("titleLabel")
        root.addWidget(title)

        # -- Paths ------------------------------------------------------
        self.pick_input  = PathPicker("Source folder", "Folder to scan for photos/videos")
        self.pick_output = PathPicker("Output folder", "Where organized media is moved to")
        self.pick_vault  = PathPicker("Vault root", "Obsidian vault (notes go to <vault>/photo-notes)")
        for p in (self.pick_input, self.pick_output, self.pick_vault):
            root.addWidget(p)

        root.addWidget(_hline())

        # -- Options ------------------------------------------------------
        opts_label = QLabel("OPTIONS")
        opts_label.setObjectName("sectionLabel")
        root.addWidget(opts_label)

        self.chk_dry_run    = QCheckBox("Dry run (simulate, don't move files or write notes)")
        self.chk_skip_ai    = QCheckBox("Skip AI scene tagging (CLIP)")
        self.chk_skip_faces = QCheckBox("Skip face detection")
        self.chk_skip_video = QCheckBox("Skip video files")
        self.chk_skip_phash = QCheckBox("Skip perceptual-hash near-duplicate detection")
        self.chk_no_integrity = QCheckBox("Skip integrity report")
        for c in (self.chk_dry_run, self.chk_skip_ai, self.chk_skip_faces,
                  self.chk_skip_video, self.chk_skip_phash, self.chk_no_integrity):
            root.addWidget(c)

        # -- Duplicate handling --------------------------------------------
        dup_row = QHBoxLayout()
        dup_row.setSpacing(10)
        dup_lbl = QLabel("On duplicate:")
        dup_row.addWidget(dup_lbl)
        self.combo_dup_action = QComboBox()
        self.combo_dup_action.addItems(["skip (leave in place)", "move (to duplicates/)", "trash (delete)"])
        self.combo_dup_action.setFixedWidth(220)
        dup_row.addWidget(self.combo_dup_action)
        dup_row.addStretch(1)
        root.addLayout(dup_row)

        root.addWidget(_hline())

        # -- Advanced ------------------------------------------------------
        adv_label = QLabel("ADVANCED")
        adv_label.setObjectName("sectionLabel")
        root.addWidget(adv_label)

        adv_row = QHBoxLayout()
        adv_row.setSpacing(20)

        adv_row.addWidget(QLabel("pHash threshold"))
        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(0, 32)
        self.spin_threshold.setToolTip("Hamming distance; 0 = identical, higher = more lenient near-dup matching")
        adv_row.addWidget(self.spin_threshold)

        adv_row.addWidget(QLabel("I/O workers"))
        self.spin_io_workers = QSpinBox()
        self.spin_io_workers.setRange(0, 64)
        self.spin_io_workers.setSpecialValueText("auto")
        adv_row.addWidget(self.spin_io_workers)

        adv_row.addWidget(QLabel("AI workers"))
        self.spin_ai_workers = QSpinBox()
        self.spin_ai_workers.setRange(0, 64)
        self.spin_ai_workers.setSpecialValueText("auto")
        adv_row.addWidget(self.spin_ai_workers)

        adv_row.addStretch(1)
        root.addLayout(adv_row)

        root.addWidget(_hline())

        # -- Run button + progress -----------------------------------------
        run_row = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_run.setObjectName("primary")
        self.btn_run.setMinimumHeight(38)
        self.btn_run.setMinimumWidth(140)
        self.btn_run.clicked.connect(self._on_run_clicked)
        run_row.addWidget(self.btn_run)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("")
        root.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setObjectName("hintLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        root.addStretch(1)
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Prefs <-> widgets ────────────────────────────────────────────────
    def _load_prefs(self) -> None:
        p = self.prefs
        self.pick_input.setText(p.input)
        self.pick_output.setText(p.output)
        self.pick_vault.setText(p.vault)
        self.chk_dry_run.setChecked(p.dry_run)
        self.chk_skip_ai.setChecked(p.skip_ai)
        self.chk_skip_faces.setChecked(p.skip_faces)
        self.chk_skip_video.setChecked(p.skip_video)
        self.chk_skip_phash.setChecked(p.skip_phash)
        self.chk_no_integrity.setChecked(p.no_integrity)
        self.combo_dup_action.setCurrentIndex({"skip": 0, "move": 1, "trash": 2}.get(p.dup_action, 0))
        self.spin_threshold.setValue(p.threshold)
        self.spin_io_workers.setValue(p.io_workers)
        self.spin_ai_workers.setValue(p.ai_workers)

    def save_to_prefs(self) -> None:
        p = self.prefs
        p.input        = self.pick_input.text()
        p.output       = self.pick_output.text()
        p.vault        = self.pick_vault.text()
        p.dry_run      = self.chk_dry_run.isChecked()
        p.skip_ai      = self.chk_skip_ai.isChecked()
        p.skip_faces   = self.chk_skip_faces.isChecked()
        p.skip_video   = self.chk_skip_video.isChecked()
        p.skip_phash   = self.chk_skip_phash.isChecked()
        p.no_integrity = self.chk_no_integrity.isChecked()
        p.dup_action   = ["skip", "move", "trash"][self.combo_dup_action.currentIndex()]
        p.threshold    = self.spin_threshold.value()
        p.io_workers   = self.spin_io_workers.value()
        p.ai_workers   = self.spin_ai_workers.value()
        p.save()

    # ── Run lifecycle ────────────────────────────────────────────────────
    def _on_run_clicked(self) -> None:
        errors = []
        if not self.pick_input.text():
            errors.append("Source folder is required.")
        if not self.pick_output.text():
            errors.append("Output folder is required.")
        if not self.pick_vault.text():
            errors.append("Vault root is required.")
        if errors:
            QMessageBox.warning(self, "Missing information", "\n".join(errors))
            return

        dup_action = ["skip", "move", "trash"][self.combo_dup_action.currentIndex()]
        if dup_action == "trash" and not self.chk_dry_run.isChecked():
            confirm = QMessageBox.warning(
                self, "Confirm permanent delete",
                "Duplicate handling is set to 'trash' — matched duplicates "
                "will be permanently deleted, not moved to a folder. "
                "This can't be undone. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        self.save_to_prefs()

        kwargs = dict(
            input_dir  = Path(self.pick_input.text()),
            output_dir = Path(self.pick_output.text()),
            vault_root = Path(self.pick_vault.text()),
            dry_run    = self.chk_dry_run.isChecked(),
            skip_ai    = self.chk_skip_ai.isChecked(),
            skip_faces = self.chk_skip_faces.isChecked(),
            skip_video = self.chk_skip_video.isChecked(),
            dup_action = dup_action,
            skip_phash = self.chk_skip_phash.isChecked(),
            integrity_report = not self.chk_no_integrity.isChecked(),
            io_workers = self.spin_io_workers.value() or None,
            ai_workers = self.spin_ai_workers.value() or None,
            phash_threshold = self.spin_threshold.value(),
        )
        self.set_running(True)
        self.run_requested.emit(kwargs)

    def set_running(self, running: bool) -> None:
        self.btn_run.setText("Running…" if running else "Run")
        self.btn_run.setEnabled(not running)
        for w in (self.pick_input, self.pick_output, self.pick_vault,
                  self.chk_dry_run, self.chk_skip_ai, self.chk_skip_faces,
                  self.chk_skip_video, self.chk_skip_phash, self.chk_no_integrity,
                  self.combo_dup_action, self.spin_threshold,
                  self.spin_io_workers, self.spin_ai_workers):
            w.setEnabled(not running)
        if running:
            self.progress.setRange(0, 0)   # indeterminate until first item
            self.status_label.setText("Starting…")

    def set_progress(self, current: int, total: int) -> None:
        if total <= 0:
            return
        if self.progress.maximum() != total:
            self.progress.setRange(0, total)
        self.progress.setValue(current)
        self.progress.setFormat(f"{current}/{total}")
        self.status_label.setText(f"Processing {current} of {total}…")

    def on_finished(self, summary: RunSummary) -> None:
        self.set_running(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        parts = [f"{summary.notes_written} note(s) written"]
        if summary.duplicates_found:
            parts.append(f"{summary.duplicates_found} duplicate(s) found")
        if summary.has_problems:
            parts.append("⚠ problems detected — see Logs")
        self.progress.setFormat(" · ".join(parts))
        self.status_label.setText(
            f"Done{' (dry run)' if summary.dry_run else ''} — " + ", ".join(parts))

    def on_failed(self, message: str) -> None:
        self.set_running(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Failed")
        self.status_label.setText(f"Run failed: {message}")
        QMessageBox.critical(self, "Run failed", message)
