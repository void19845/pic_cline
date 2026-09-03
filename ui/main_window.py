from __future__ import annotations
"""ui.main_window — application shell. Thin: wires tabs to the pipeline bridge, nothing else."""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from organizer.reporting import RunSummary
from ui.pipeline_bridge import PipelineController
from ui.prefs import Prefs
from ui.tabs.faces_tab import FacesTab
from ui.tabs.logs_tab import LogsTab
from ui.tabs.review_tab import ReviewTab
from ui.tabs.run_tab import RunTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo Organizer")
        self.resize(980, 760)

        self.prefs = Prefs.load()
        self.controller = PipelineController()

        self.run_tab    = RunTab(self.prefs)
        self.logs_tab   = LogsTab()
        self.review_tab = ReviewTab()
        self.faces_tab  = FacesTab()

        tabs = QTabWidget()
        tabs.addTab(self.run_tab, "Run")
        tabs.addTab(self.logs_tab, "Logs")
        tabs.addTab(self.review_tab, "Review Duplicates")
        tabs.addTab(self.faces_tab, "Faces")
        self.setCentralWidget(tabs)

        self._wire_signals()
        self._sync_vault_dependent_tabs()

    def _wire_signals(self) -> None:
        self.run_tab.run_requested.connect(self._start_run)

        self.controller.log_line.connect(self.logs_tab.append)
        self.controller.progress.connect(self.run_tab.set_progress)
        self.controller.run_finished.connect(self._on_run_finished)
        self.controller.run_failed.connect(self.run_tab.on_failed)

        # Vault root may change any time the user edits the field — keep
        # Review/Faces pointed at whatever's currently typed.
        self.run_tab.pick_vault.changed.connect(self._on_vault_changed)

    def _on_vault_changed(self, text: str) -> None:
        if text.strip():
            self._set_vault_root(Path(text.strip()))

    def _sync_vault_dependent_tabs(self) -> None:
        if self.prefs.vault:
            self._set_vault_root(Path(self.prefs.vault))

    def _set_vault_root(self, vault_root: Path) -> None:
        self.review_tab.set_vault_root(vault_root)
        self.faces_tab.set_vault_root(vault_root)

    def _start_run(self, kwargs: dict) -> None:
        # phash_threshold is process-global state in organizer.duplicates
        # (pre-existing design, not something this UI layer changes) —
        # set it here, right before the run starts.
        threshold = kwargs.pop("phash_threshold", None)
        if threshold is not None:
            import organizer.duplicates as _dup
            _dup.PHASH_THRESHOLD = threshold

        self.logs_tab.clear()
        started = self.controller.start(**kwargs)
        if not started:
            QMessageBox.information(self, "Already running", "A run is already in progress.")

    def _on_run_finished(self, summary: RunSummary) -> None:
        self.run_tab.on_finished(summary)
        vault_text = self.run_tab.pick_vault.text()
        if vault_text:
            self._set_vault_root(Path(vault_text))

    def closeEvent(self, event) -> None:
        if self.controller.is_running:
            confirm = QMessageBox.warning(
                self, "Run in progress",
                "A run is still in progress. Quitting now may leave the "
                "vault in a partially-written state. Quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.run_tab.save_to_prefs()
        event.accept()
