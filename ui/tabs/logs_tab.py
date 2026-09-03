from __future__ import annotations
"""ui.tabs.logs_tab — live log view, fed directly by PipelineController signals."""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)


class LogsTab(QWidget):
    """
    No polling, no stdout parsing: MainWindow connects
    controller.log_line -> self.append directly. Each line lands here the
    moment organizer/ calls reporter.log(), regardless of which worker
    thread produced it (Qt marshals the cross-thread signal for us).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Logs")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch(1)

        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("ghost")
        btn_clear.clicked.connect(self.clear)
        header.addWidget(btn_clear)

        btn_save = QPushButton("Save to file…")
        btn_save.setObjectName("ghost")
        btn_save.clicked.connect(self._save)
        header.addWidget(btn_save)

        root.addLayout(header)

        self.view = QPlainTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setMaximumBlockCount(20000)   # cap memory on very long runs
        root.addWidget(self.view, 1)

    def append(self, message: str) -> None:
        self.view.appendPlainText(message)
        self.view.moveCursor(QTextCursor.MoveOperation.End)

    def clear(self) -> None:
        self.view.clear()

    def _save(self) -> None:
        default_name = f"photo_organizer_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Save log", default_name, "Text files (*.txt)")
        if path:
            Path(path).write_text(self.view.toPlainText(), encoding="utf-8")
