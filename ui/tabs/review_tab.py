from __future__ import annotations
"""
ui.tabs.review_tab — duplicate pair review.

Rebuilt on organizer.dup_report (load_pending / resolve_pair), the
Markdown-based system pipeline.py already writes to on every run. The old
Tkinter UI's Review tab queried a `duplicates` SQLite table that
init_db() never created (confirmed broken independent of the Phase 1
migration) -- this tab replaces that with the system that actually works.

Design choice, spelled out because it's a real simplification versus the
old tab: pairs shown here have ALREADY been through the pipeline's
automatic (higher-resolution-wins) decision. This tab lets you delete the
losing copy if it's still on disk (dup_action=skip leaves it in the
source folder untouched) or dismiss the pair. It does not attempt to
"swap" which copy was kept -- that would mean undoing an already-written
note and a completed file move, which is a bigger, riskier operation than
a review screen should do silently. If you need that, do it manually and
dismiss the pair.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from organizer.dup_report import DupPair, load_pending, resolve_pair

_THUMB = 160


def _thumb(path_str: str) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(_THUMB, _THUMB)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("background-color: #25252d; border-radius: 6px; border: 1px solid #2e2e38;")
    path = Path(path_str)
    if path.exists():
        pix = QPixmap(str(path))
        if not pix.isNull():
            lbl.setPixmap(pix.scaled(
                _THUMB, _THUMB,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            return lbl
    lbl.setText("missing\nfile")
    lbl.setStyleSheet(lbl.styleSheet() + "color: #5a5870;")
    return lbl


class _PairCard(QFrame):
    def __init__(self, pair: DupPair, vault_root: Path, on_resolved, parent=None) -> None:
        super().__init__(parent)
        self.pair = pair
        self.vault_root = vault_root
        self.on_resolved = on_resolved
        self.setObjectName("card")
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(10)

        # -- thumbnails + info row --------------------------------------
        row = QHBoxLayout()
        row.setSpacing(16)

        orig_col = QVBoxLayout()
        orig_col.addWidget(_thumb(self.pair.path_original), 0, Qt.AlignmentFlag.AlignHCenter)
        orig_lbl = QLabel(f"Original\n{Path(self.pair.path_original).name}\n"
                           f"{self.pair.res_original} · {self.pair.size_original}")
        orig_lbl.setObjectName("hintLabel")
        orig_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        orig_lbl.setWordWrap(True)
        orig_col.addWidget(orig_lbl)
        row.addLayout(orig_col)

        mid_col = QVBoxLayout()
        kind_lbl = QLabel("EXACT" if self.pair.kind == "exact" else
                           f"NEAR (Δ{self.pair.phash_distance})")
        kind_lbl.setObjectName("pillDup")
        kind_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        mid_col.addWidget(kind_lbl)
        arrow = QLabel("=")
        arrow.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        arrow.setStyleSheet("color: #5a5870; font-size: 20px;")
        mid_col.addWidget(arrow)
        mid_col.addStretch(1)
        row.addLayout(mid_col)

        dup_exists = Path(self.pair.path_duplicate).exists()
        dup_col = QVBoxLayout()
        dup_col.addWidget(_thumb(self.pair.path_duplicate), 0, Qt.AlignmentFlag.AlignHCenter)
        dup_status = "" if dup_exists else "  (already moved/deleted)"
        dup_lbl = QLabel(f"Duplicate\n{Path(self.pair.path_duplicate).name}\n"
                          f"{self.pair.res_duplicate} · {self.pair.size_duplicate}{dup_status}")
        dup_lbl.setObjectName("hintLabel")
        dup_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        dup_lbl.setWordWrap(True)
        dup_col.addWidget(dup_lbl)
        row.addLayout(dup_col)

        row.addStretch(1)
        outer.addLayout(row)

        # -- meta line -----------------------------------------------------
        meta = QLabel(f"Detected {self.pair.detected_at}")
        meta.setObjectName("hintLabel")
        outer.addWidget(meta)

        # -- actions ---------------------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(8)

        btn_delete = QPushButton("Delete duplicate file")
        btn_delete.setObjectName("danger")
        btn_delete.setEnabled(dup_exists)
        btn_delete.setToolTip(
            "Permanently delete the duplicate copy from disk"
            if dup_exists else
            "File no longer at the recorded path (already moved or removed) — nothing to delete")
        btn_delete.clicked.connect(self._delete_duplicate)
        actions.addWidget(btn_delete)

        btn_dismiss = QPushButton("Dismiss")
        btn_dismiss.setObjectName("ghost")
        btn_dismiss.clicked.connect(lambda: self._resolve("dismissed"))
        actions.addWidget(btn_dismiss)

        actions.addStretch(1)
        outer.addLayout(actions)

    def _delete_duplicate(self) -> None:
        confirm = QMessageBox.warning(
            self, "Delete file",
            f"Permanently delete:\n{self.pair.path_duplicate}\n\nThis can't be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            Path(self.pair.path_duplicate).unlink(missing_ok=True)
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        self._resolve("duplicate_deleted")

    def _resolve(self, status: str) -> None:
        resolve_pair(self.vault_root, self.pair.key, status)
        self.on_resolved()


class ReviewTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault_root: Path | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Review Duplicates")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("ghost")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        root.addLayout(header)

        self.count_label = QLabel("")
        self.count_label.setObjectName("hintLabel")
        root.addWidget(self.count_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch(1)
        self.scroll.setWidget(self._list_container)
        root.addWidget(self.scroll, 1)

    def set_vault_root(self, vault_root: Path) -> None:
        self._vault_root = vault_root
        self.refresh()

    def refresh(self) -> None:
        # Clear existing cards (everything except the trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._vault_root is None or not (self._vault_root / "duplicates_report.md").exists():
            self.count_label.setText("No duplicates_report.md yet — run the organizer first.")
            return

        pairs = load_pending(self._vault_root)
        self.count_label.setText(
            f"{len(pairs)} pending pair(s)" if pairs else "No pending duplicates 🎉")

        for pair in pairs:
            card = _PairCard(pair, self._vault_root, self.refresh)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
