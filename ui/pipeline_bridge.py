from __future__ import annotations
"""
ui.pipeline_bridge — the ONLY file where PyQt6 and organizer/ meet.

QtReporter satisfies organizer.reporting.ProgressReporter structurally
(log/progress/finished) by emitting Qt signals instead of printing.
PipelineWorker runs process_vault() on a background QThread so the UI
event loop is never blocked -- this replaces the old subprocess +
stdout-regex approach entirely: the pipeline runs in-process, and the
UI only ever reacts to signals.

Threading pattern: QObject.moveToThread(), not QThread subclassing --
this is the pattern Qt's own docs recommend. MainWindow owns the
QThread; PipelineWorker/QtReporter live on it.
"""

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from organizer.dup_report import DupPair
from organizer.integrity import IntegrityRecord
from organizer.pipeline import process_vault
from organizer.reporting import RunSummary


class QtReporter(QObject):
    """
    Implements organizer.reporting.ProgressReporter's shape (log/progress/
    finished) via signals. Not a subclass of the Protocol -- Protocol is
    structural, and QObject's metaclass shouldn't be asked to also satisfy
    Python's typing machinery.

    Emitted from a worker thread; Qt auto-queues these to the main thread
    for any slot connected without Qt.ConnectionType.DirectConnection, so
    ordinary `signal.connect(slot)` in MainWindow is safe as-is.
    """
    log_line      = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)         # current, total
    run_finished  = pyqtSignal(object)             # RunSummary
    run_failed    = pyqtSignal(str)                # unhandled exception message

    def log(self, message: str) -> None:
        self.log_line.emit(message)

    # Method name must be exactly `progress` to satisfy ProgressReporter's
    # structural contract (process_vault calls reporter.progress(cur, tot)).
    # The signal is named progress_signal precisely so this method and the
    # signal don't collide on the same class attribute name.
    def progress(self, current: int, total: int) -> None:
        self.progress_signal.emit(current, total)

    def finished(self, summary: RunSummary) -> None:
        self.run_finished.emit(summary)


class PipelineWorker(QObject):
    """
    Lives on a background QThread. run() calls process_vault() exactly
    once and reports outcome via QtReporter's signals (success) or
    run_failed (unhandled exception -- process_vault() itself only raises
    for programmer errors; expected failures are already captured per-item
    inside WorkerResult and don't reach here).
    """

    def __init__(self, reporter: QtReporter, run_kwargs: dict[str, Any]) -> None:
        super().__init__()
        self._reporter    = reporter
        self._run_kwargs  = run_kwargs

    def run(self) -> None:
        try:
            process_vault(reporter=self._reporter, **self._run_kwargs)
        except Exception as exc:
            self._reporter.run_failed.emit(str(exc))


class PipelineController(QObject):
    """
    Owns the QThread + PipelineWorker + QtReporter lifecycle so MainWindow
    doesn't have to juggle thread plumbing directly. One controller per
    MainWindow; start() is a no-op if a run is already active.

    Usage:
        controller = PipelineController()
        controller.log_line.connect(logs_tab.append)
        controller.progress.connect(run_tab.set_progress)
        controller.run_finished.connect(run_tab.on_finished)
        controller.run_failed.connect(run_tab.on_failed)
        controller.start(input_dir=..., output_dir=..., vault_root=..., ...)
    """
    log_line     = pyqtSignal(str)
    progress     = pyqtSignal(int, int)
    run_finished = pyqtSignal(object)
    run_failed   = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._thread:   QThread | None = None
        self._worker:   PipelineWorker | None = None
        self._reporter: QtReporter | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, **run_kwargs: Any) -> bool:
        """Returns False (no-op) if a run is already in progress."""
        if self.is_running:
            return False

        self._reporter = QtReporter()
        self._reporter.log_line.connect(self.log_line.emit)
        self._reporter.progress_signal.connect(self.progress.emit)
        self._reporter.run_finished.connect(self._on_finished)
        self._reporter.run_failed.connect(self._on_failed)

        self._thread = QThread()
        self._worker = PipelineWorker(self._reporter, run_kwargs)
        self._worker.moveToThread(self._thread)
        self._reporter.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._thread.start()
        return True

    def _on_finished(self, summary: RunSummary) -> None:
        self.run_finished.emit(summary)
        self._teardown()

    def _on_failed(self, message: str) -> None:
        self.run_failed.emit(message)
        self._teardown()

    def _teardown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread   = None
        self._worker   = None
        self._reporter = None
