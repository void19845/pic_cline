#!/usr/bin/env python3
"""
duplicate_reviewer.py
=====================
Side-by-side viewer for near-duplicate photos detected by photo_organizer.

Shows each duplicate pair with:
  • Thumbnail previews (scaled to fit)
  • File name, size, resolution, date
  • SHA-256 match type (EXACT / NEAR)
  • Three action buttons: Keep Left, Keep Right, Keep Both

Decisions are applied immediately (the rejected file is moved to
<vault>/duplicates/reviewed/ or deleted, depending on your choice).

Usage
-----
    python duplicate_reviewer.py --vault ~/path/to/vault
    python duplicate_reviewer.py --vault ~/path/to/vault --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox

# ── Palette (matches photo_organizer_ui.py) ──────────────────────────────────
BG      = "#0f0f11"
BG2     = "#1a1a1f"
BG3     = "#25252d"
BORDER  = "#2e2e38"
ACCENT  = "#7c6af7"
ACCENT2 = "#5dcaa5"
DANGER  = "#e05b5b"
WARN    = "#f0c060"
FG      = "#e8e6f0"
FG2     = "#8e8ba0"
FG3     = "#5a5870"
MONO    = "Courier New"

THUMB_W = 380
THUMB_H = 320


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(path: Path) -> str:
    try:
        b = path.stat().st_size
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except Exception:
        return "?"


def _img_info(path: Path) -> tuple[int, int]:
    """Return (width, height) or (0, 0)."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.width, img.height
    except Exception:
        return 0, 0


def _load_thumb(path: Path, max_w: int = THUMB_W, max_h: int = THUMB_H):
    """Return a PIL ImageTk.PhotoImage scaled to fit the thumbnail box."""
    try:
        from PIL import Image, ImageTk
        img = Image.open(path).convert("RGB")
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


# ── Database helpers ──────────────────────────────────────────────────────────

def load_pairs(db_path: Path) -> list[dict]:
    """
    Load unreviewed duplicate pairs from the database.

    A pair is returned as::

        {
          "id":       int,
          "path":     str,   # the duplicate
          "original": str,   # the kept original
          "kind":     str,   # "exact" | "perceptual"
          "action":   str,   # "skip" | "move" | "trash"
          "kept":     bool,
        }
    """
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, path, original, kind, action, kept
           FROM duplicates
           WHERE action = 'skip'       -- only unactioned pairs need review
           ORDER BY id"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_reviewed(db_path: Path, dup_id: int, final_action: str) -> None:
    """Update the action field after the user makes a decision."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE duplicates SET action = ? WHERE id = ?",
        (final_action, dup_id),
    )
    conn.commit()
    conn.close()


# ── Main window ───────────────────────────────────────────────────────────────

class DuplicateReviewer(tk.Tk):
    def __init__(self, vault_root: Path, dry_run: bool = False):
        super().__init__()
        self.vault_root  = vault_root
        self.dry_run     = dry_run
        self.db_path     = vault_root / "photo_organizer.db"
        self.review_dir  = vault_root / "duplicates" / "reviewed"

        self.title("Duplicate Reviewer")
        self.geometry("900x700")
        self.minsize(700, 500)
        self.configure(bg=BG)

        self.pairs: list[dict] = []
        self.idx:   int        = 0
        self._thumbs: list     = []   # keep references to prevent GC

        self._build_ui()
        self.after(50, self._load_pairs)

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        bar = tk.Frame(self, bg=BG2, height=48)
        bar.pack(fill="x")
        bar.columnconfigure(1, weight=1)
        tk.Label(bar, text="Duplicate Reviewer", bg=BG2, fg=FG,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=12)
        self._counter = tk.Label(bar, text="Loading…", bg=BG2, fg=FG2,
                                  font=("Segoe UI", 9))
        self._counter.pack(side="right", padx=16)

        if self.dry_run:
            tk.Label(bar, text="DRY RUN", bg=BG2, fg=WARN,
                     font=("Segoe UI", 8, "bold")).pack(side="right", padx=8)

        # Main split: left photo | right photo
        split = tk.Frame(self, bg=BG)
        split.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        split.columnconfigure(0, weight=1)
        split.columnconfigure(1, weight=1)
        split.rowconfigure(0, weight=1)

        self._left_panel  = self._photo_panel(split, 0, "Original")
        self._right_panel = self._photo_panel(split, 1, "Duplicate")

        # Type badge row
        badge_row = tk.Frame(self, bg=BG)
        badge_row.pack(pady=4)
        self._badge = tk.Label(badge_row, text="", bg=BG, fg=FG3,
                                font=("Segoe UI", 9))
        self._badge.pack()

        # Action buttons
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(4, 14))

        self._btn_left = tk.Button(
            btn_row, text="← Keep original",
            command=self._keep_left,
            bg=ACCENT2, fg="#fff", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            activebackground="#3aaa85", padx=20, pady=10,
        )
        self._btn_left.grid(row=0, column=0, padx=6)

        self._btn_both = tk.Button(
            btn_row, text="Keep both",
            command=self._keep_both,
            bg=BG3, fg=FG, relief="flat", bd=0,
            font=("Segoe UI", 10), cursor="hand2",
            activebackground=BORDER, padx=20, pady=10,
        )
        self._btn_both.grid(row=0, column=1, padx=6)

        self._btn_right = tk.Button(
            btn_row, text="Keep duplicate →",
            command=self._keep_right,
            bg=ACCENT, fg="#fff", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            activebackground="#6657d4", padx=20, pady=10,
        )
        self._btn_right.grid(row=0, column=2, padx=6)

        self._btn_skip = tk.Button(
            btn_row, text="Skip →",
            command=self._skip,
            bg=BG3, fg=FG3, relief="flat", bd=0,
            font=("Segoe UI", 9), cursor="hand2",
            activebackground=BORDER, padx=14, pady=10,
        )
        self._btn_skip.grid(row=0, column=3, padx=(18, 0))

        # Keyboard shortcuts
        self.bind("<Left>",  lambda _: self._keep_left())
        self.bind("<Right>", lambda _: self._keep_right())
        self.bind("<Up>",    lambda _: self._keep_both())
        self.bind("<space>", lambda _: self._skip())

    def _photo_panel(self, parent: tk.Frame, col: int, role: str) -> dict:
        """Create one photo panel (thumbnail + metadata). Returns handle dict."""
        frame = tk.Frame(parent, bg=BG2, bd=0,
                         highlightthickness=1,
                         highlightbackground=BORDER)
        frame.grid(row=0, column=col, sticky="nsew",
                   padx=(0 if col else 0, 6 if col == 0 else 0))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # Role label
        tk.Label(frame, text=role, bg=BG2, fg=FG3,
                 font=("Segoe UI", 8, "bold"),
                 anchor="center").grid(row=0, column=0, sticky="ew", pady=(8, 0))

        # Thumbnail canvas
        canvas = tk.Canvas(frame, bg=BG, width=THUMB_W, height=THUMB_H,
                           highlightthickness=0, bd=0)
        canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        # Metadata labels
        meta_frame = tk.Frame(frame, bg=BG2)
        meta_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 10))
        meta_frame.columnconfigure(0, weight=1)

        name_lbl = tk.Label(meta_frame, text="", bg=BG2, fg=FG,
                             font=("Segoe UI", 9, "bold"),
                             anchor="w", wraplength=THUMB_W - 16)
        name_lbl.grid(row=0, column=0, sticky="w")

        info_lbl = tk.Label(meta_frame, text="", bg=BG2, fg=FG2,
                             font=("Segoe UI", 8), anchor="w",
                             justify="left")
        info_lbl.grid(row=1, column=0, sticky="w")

        path_lbl = tk.Label(meta_frame, text="", bg=BG2, fg=FG3,
                             font=(MONO, 7), anchor="w",
                             wraplength=THUMB_W - 16)
        path_lbl.grid(row=2, column=0, sticky="w")

        return {
            "frame": frame, "canvas": canvas,
            "name": name_lbl, "info": info_lbl, "path": path_lbl,
        }

    # ── Load & render ─────────────────────────────────────────────────────

    def _load_pairs(self):
        self.pairs = load_pairs(self.db_path)
        if not self.pairs:
            self._show_empty()
            return
        self.idx = 0
        self._render_current()

    def _render_current(self):
        if self.idx >= len(self.pairs):
            self._show_done()
            return

        pair    = self.pairs[self.idx]
        left_p  = Path(pair["original"])
        right_p = Path(pair["path"])
        kind    = pair["kind"].upper()

        self._counter.config(
            text=f"{self.idx + 1} / {len(self.pairs)}  unreviewed"
        )
        self._badge.config(
            text=f"{kind} duplicate  (id {pair['id']})",
            fg=DANGER if kind == "EXACT" else WARN,
        )

        self._thumbs.clear()
        self._render_panel(self._left_panel,  left_p,  "original")
        self._render_panel(self._right_panel, right_p, "duplicate")

        # Highlight the higher-res side
        self._highlight_better(left_p, right_p)

    def _render_panel(self, panel: dict, path: Path, role: str):
        canvas: tk.Canvas = panel["canvas"]
        canvas.delete("all")

        if not path.exists():
            canvas.create_text(
                THUMB_W // 2, THUMB_H // 2,
                text=f"File not found\n{path.name}",
                fill=DANGER, font=("Segoe UI", 10), justify="center",
            )
            panel["name"].config(text=path.name)
            panel["info"].config(text="MISSING")
            panel["path"].config(text=str(path))
            return

        # Load thumbnail in background thread to keep UI responsive
        def _bg():
            thumb = _load_thumb(path)
            self.after(0, lambda: _paint(thumb))

        def _paint(thumb):
            canvas.delete("all")
            if thumb:
                self._thumbs.append(thumb)
                x = THUMB_W // 2
                y = THUMB_H // 2
                canvas.create_image(x, y, anchor="center", image=thumb)
            else:
                canvas.create_text(
                    THUMB_W // 2, THUMB_H // 2,
                    text="Preview unavailable",
                    fill=FG3, font=("Segoe UI", 10),
                )

        threading.Thread(target=_bg, daemon=True).start()

        # Metadata
        w, h   = _img_info(path)
        size   = _fmt_size(path)
        res    = f"{w}×{h}" if w else "?"
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime
                                           ).strftime("%Y-%m-%d %H:%M")
        except Exception:
            mtime = "?"

        panel["name"].config(text=path.name)
        panel["info"].config(text=f"{res}  ·  {size}  ·  {mtime}")
        panel["path"].config(text=str(path.parent))

    def _highlight_better(self, left_p: Path, right_p: Path):
        """Put a coloured border on the higher-resolution side."""
        try:
            lw, lh = _img_info(left_p)
            rw, rh = _img_info(right_p)
            if lw * lh > rw * rh:
                self._left_panel["frame"].config(
                    highlightbackground=ACCENT2)
                self._right_panel["frame"].config(
                    highlightbackground=BORDER)
            elif rw * rh > lw * lh:
                self._left_panel["frame"].config(
                    highlightbackground=BORDER)
                self._right_panel["frame"].config(
                    highlightbackground=ACCENT2)
            else:
                for panel in (self._left_panel, self._right_panel):
                    panel["frame"].config(highlightbackground=BORDER)
        except Exception:
            pass

    # ── Actions ───────────────────────────────────────────────────────────

    def _current_pair(self) -> dict:
        return self.pairs[self.idx]

    def _delete_file(self, path: Path, label: str):
        """Move *path* to the reviewed/ trash folder."""
        if self.dry_run:
            print(f"[dry-run] would remove {label}: {path}")
            return
        if not path.exists():
            return
        try:
            self.review_dir.mkdir(parents=True, exist_ok=True)
            dest = self.review_dir / path.name
            counter = 1
            while dest.exists():
                dest = self.review_dir / f"{path.stem}_{counter}{path.suffix}"
                counter += 1
            shutil.move(str(path), dest)
            print(f"  moved {label} → {dest}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not move {path.name}:\n{e}")

    def _advance(self, final_action: str):
        pair = self._current_pair()
        if not self.dry_run:
            mark_reviewed(self.db_path, pair["id"], final_action)
        self.idx += 1
        self._render_current()

    def _keep_left(self):
        """Delete the duplicate (right), keep the original (left)."""
        pair = self._current_pair()
        self._delete_file(Path(pair["path"]), "duplicate")
        self._advance("reviewed-keep-original")

    def _keep_right(self):
        """Delete the original (left), keep the duplicate (right)."""
        pair = self._current_pair()
        self._delete_file(Path(pair["original"]), "original")
        self._advance("reviewed-keep-duplicate")

    def _keep_both(self):
        """Do nothing — keep both files."""
        self._advance("reviewed-keep-both")

    def _skip(self):
        """Skip this pair for now (leave action = 'skip' in DB)."""
        self.idx += 1
        self._render_current()

    # ── Terminal states ───────────────────────────────────────────────────

    def _show_empty(self):
        for panel in (self._left_panel, self._right_panel):
            panel["canvas"].delete("all")
            panel["canvas"].create_text(
                THUMB_W // 2, THUMB_H // 2,
                text="No duplicate pairs found.\n\nRun photo_organizer.py first.",
                fill=FG3, font=("Segoe UI", 10), justify="center",
            )
        self._counter.config(text="0 pairs")
        self._badge.config(text="Nothing to review", fg=FG3)
        for b in (self._btn_left, self._btn_both,
                  self._btn_right, self._btn_skip):
            b.config(state="disabled")

    def _show_done(self):
        for panel in (self._left_panel, self._right_panel):
            panel["canvas"].delete("all")
            panel["canvas"].create_text(
                THUMB_W // 2, THUMB_H // 2,
                text="All pairs reviewed!",
                fill=ACCENT2, font=("Segoe UI", 13, "bold"), justify="center",
            )
            panel["name"].config(text="")
            panel["info"].config(text="")
            panel["path"].config(text="")
        self._counter.config(text=f"{len(self.pairs)} pairs reviewed")
        self._badge.config(text="", fg=FG3)
        for b in (self._btn_left, self._btn_both,
                  self._btn_right, self._btn_skip):
            b.config(state="disabled")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Side-by-side duplicate photo reviewer")
    p.add_argument("--vault",    required=True, help="Obsidian vault root")
    p.add_argument("--dry-run",  action="store_true",
                   help="Preview decisions without moving files")
    args = p.parse_args()

    vault_root = Path(args.vault).expanduser().resolve()
    if not vault_root.exists():
        print(f"Vault not found: {vault_root}", file=sys.stderr)
        sys.exit(1)

    app = DuplicateReviewer(vault_root, dry_run=args.dry_run)
    app.mainloop()


if __name__ == "__main__":
    main()
