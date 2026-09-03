from __future__ import annotations
"""ui.widgets.path_picker — a labeled path field + Browse button row."""

from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import pyqtSignal


class PathPicker(QWidget):
    """
    Label above a [QLineEdit][Browse] row. Emits changed(str) whenever the
    path text changes, whether typed or picked via the dialog.
    """
    changed = pyqtSignal(str)

    def __init__(
        self,
        label: str,
        placeholder: str = "",
        directory: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._directory = directory

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        lbl = QLabel(label)
        lbl.setObjectName("sectionLabel")
        outer.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(6)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed.emit)
        row.addWidget(self.edit, 1)

        browse = QPushButton("Browse…")
        browse.setObjectName("ghost")
        browse.setFixedWidth(84)
        browse.clicked.connect(self._pick)
        row.addWidget(browse)

        outer.addLayout(row)

    def _pick(self) -> None:
        if self._directory:
            path = QFileDialog.getExistingDirectory(self, "Select folder", self.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select file", self.text())
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value)
