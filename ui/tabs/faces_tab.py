from __future__ import annotations
"""ui.tabs.faces_tab — face label editor (face_labels.json + maintenance.apply_face_renames)."""

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from organizer.maintenance import apply_face_renames


class FacesTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault_root: Path | None = None
        self._edits: dict[str, QLineEdit] = {}
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Faces")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch(1)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setObjectName("ghost")
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh)

        self.btn_apply = QPushButton("Apply renames")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.clicked.connect(self._apply)
        header.addWidget(self.btn_apply)
        root.addLayout(header)

        hint = QLabel("Rename detected face clusters — updates every photo note's "
                       "people: list and [[wikilink]] for you.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.status_label = QLabel("")
        self.status_label.setObjectName("hintLabel")
        root.addWidget(self.status_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch(1)
        self.scroll.setWidget(self._list_container)
        root.addWidget(self.scroll, 1)

    def set_vault_root(self, vault_root: Path) -> None:
        self._vault_root = vault_root
        self.refresh()

    def refresh(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._edits.clear()

        if self._vault_root is None:
            return
        labels_file = self._vault_root / "face_labels.json"
        if not labels_file.exists():
            self.status_label.setText("No face_labels.json yet — run the organizer first (with face detection enabled).")
            self.btn_apply.setEnabled(False)
            return

        try:
            data: dict[str, str] = json.loads(labels_file.read_text(encoding="utf-8"))
        except Exception as exc:
            self.status_label.setText(f"Couldn't read face_labels.json: {exc}")
            self.btn_apply.setEnabled(False)
            return

        self.btn_apply.setEnabled(bool(data))
        self.status_label.setText(f"{len(data)} face cluster(s)")

        for original_label, current_name in sorted(data.items()):
            row = QFrame()
            row.setObjectName("card")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)

            id_lbl = QLabel(original_label)
            id_lbl.setFixedWidth(160)
            id_lbl.setObjectName("hintLabel")
            row_layout.addWidget(id_lbl)

            edit = QLineEdit(current_name)
            edit.setPlaceholderText("Name…")
            row_layout.addWidget(edit, 1)
            self._edits[original_label] = edit

            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _apply(self) -> None:
        if self._vault_root is None:
            return
        labels_file = self._vault_root / "face_labels.json"
        renames = {
            original: edit.text().strip()
            for original, edit in self._edits.items()
            if edit.text().strip() and edit.text().strip() != original
        }
        # Persist the full map (renamed + unchanged) back to face_labels.json
        full_map = {original: (edit.text().strip() or original)
                    for original, edit in self._edits.items()}
        try:
            labels_file.write_text(
                json.dumps(full_map, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        if not renames:
            self.status_label.setText("No changes to apply.")
            return

        notes_dir = self._vault_root / "photo-notes"
        try:
            updated = apply_face_renames(self._vault_root, notes_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Apply failed", str(exc))
            return

        self.status_label.setText(
            f"Applied {len(renames)} rename(s) across {updated} note(s).")
        self.refresh()
