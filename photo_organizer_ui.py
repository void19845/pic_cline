#!/usr/bin/env python3
"""
photo_organizer_ui.py
=====================
Desktop GUI for photo_organizer.py — fullscreen, tabbed right panel.

Tabs:
  Logs             — live output from the organiser process
  Review Dupes     — side-by-side duplicate comparison (inline)
  Rename Faces     — face label editor (inline)

Run:
    python photo_organizer_ui.py
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# ── Python interpreter resolver ───────────────────────────────────────────────

def _find_python() -> str:
    """
    Find the best available Python interpreter to run photo_organizer.py.

    Search order
    ------------
    1. sys.executable — the interpreter running the UI right now,
       if the file actually exists on disk.
    2. venv / .venv siblings of this script:
         <script_dir>/venv/Scripts/python.exe  (Windows venv)
         <script_dir>/venv/bin/python          (Unix venv)
         <script_dir>/.venv/...                (same with hidden dir)
    3. 'python' on PATH
    4. 'python3' on PATH
    5. Bare 'python.exe' / 'python3' as last resort

    The first candidate that passes ``python -c "import sys"`` is returned.
    """
    script_dir = Path(__file__).parent
    candidates: list[str] = []

    # 1. Current interpreter — only if the file actually exists
    if sys.executable and Path(sys.executable).is_file():
        candidates.append(sys.executable)

    # 2. Venv siblings
    for venv_name in ("venv", ".venv"):
        for sub in (
            "Scripts/python.exe",   # Windows
            "Scripts/python",
            "bin/python",           # Unix
            "bin/python3",
        ):
            p = script_dir / venv_name / sub
            if p.is_file():
                candidates.append(str(p))

    # 3 & 4. PATH
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    # 5. Bare fallback
    candidates.append("python.exe" if sys.platform == "win32" else "python3")

    for c in candidates:
        try:
            r = subprocess.run(
                [c, "-c", "import sys"],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                return c
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue

    return sys.executable or "python"   # give up gracefully


PYTHON = _find_python()


# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#0f0f11"
BG2     = "#1a1a1f"
BG3     = "#25252d"
BORDER  = "#2e2e38"
ACCENT  = "#7c6af7"
ACCENT2 = "#5dcaa5"
DANGER  = "#e05b5b"
WARN    = "#f0c060"
DUP_C   = "#b07cf0"
VID_C   = "#5bb8d4"
FG      = "#e8e6f0"
FG2     = "#8e8ba0"
FG3     = "#5a5870"
MONO    = "Courier New"

SIDEBAR_W = 340
THUMB_W   = 420
THUMB_H   = 300

# ── i18n bootstrap ────────────────────────────────────────────────────────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from organizer.i18n import t, set_language, detect_language, available_languages, on_language_change

# ── Reusable widget helpers ───────────────────────────────────────────────────

def _pick_dir(var: tk.StringVar, title: str = "Select folder") -> None:
    p = filedialog.askdirectory(title=title)
    if p:
        var.set(p)


def _lbl(parent, text: str, fg: str = FG2, font_size: int = 9,
          bold: bool = False) -> tk.Label:
    weight = "bold" if bold else "normal"
    return tk.Label(parent, text=text, bg=BG2, fg=fg,
                    font=("Segoe UI", font_size, weight), anchor="w")


def _section_title(parent, text: str, row: int) -> None:
    tk.Label(parent, text=text.upper(), bg=BG2, fg=ACCENT,
             font=("Segoe UI", 7, "bold"), anchor="w"
             ).grid(row=row, column=0, columnspan=2,
                    sticky="w", padx=16, pady=(14, 2))


def _separator(parent, row: int) -> None:
    tk.Frame(parent, bg=BORDER, height=1
             ).grid(row=row, column=0, columnspan=2,
                    sticky="ew", padx=16, pady=8)


def _check(parent, text: str, var: tk.BooleanVar, row: int) -> tk.Checkbutton:
    cb = tk.Checkbutton(parent, text=text, variable=var,
                        bg=BG2, fg=FG2, selectcolor=BG3,
                        activebackground=BG2, activeforeground=FG,
                        font=("Segoe UI", 9), highlightthickness=0,
                        bd=0, cursor="hand2")
    cb.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=2)
    return cb


def _btn(parent, text: str, cmd, bg: str = BG3, fg: str = FG2,
         bold: bool = False, full: bool = False, pady: int = 6) -> tk.Button:
    weight = "bold" if bold else "normal"
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg=fg, relief="flat", bd=0,
                  font=("Segoe UI", 9, weight), cursor="hand2",
                  activebackground=BORDER, activeforeground=FG,
                  padx=10, pady=pady)
    return b


def _browse_row(parent, var: tk.StringVar, row: int, title: str) -> None:
    frame = tk.Frame(parent, bg=BG2)
    frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 4))
    frame.columnconfigure(0, weight=1)
    tk.Entry(frame, textvariable=var, bg=BG3, fg=FG, insertbackground=FG,
             relief="flat", bd=0, font=("Segoe UI", 9),
             highlightthickness=1, highlightbackground=BORDER,
             highlightcolor=ACCENT
             ).grid(row=0, column=0, sticky="ew", ipady=5, padx=(0, 6))
    tk.Button(frame, text="Browse",
              command=lambda: _pick_dir(var, title),
              bg=BG3, fg=FG2, relief="flat", bd=0,
              font=("Segoe UI", 9), cursor="hand2",
              activebackground=BORDER, activeforeground=FG,
              padx=10, pady=4
              ).grid(row=0, column=1)


def _scrollable_frame(parent) -> tuple[tk.Canvas, tk.Frame]:
    """Return (canvas, inner_frame) with a 14-px scrollbar."""
    canvas = tk.Canvas(parent, bg=BG2, highlightthickness=0, bd=0)
    sb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview,
                      bg=BG3, troughcolor=BG2, width=14,
                      activebackground=ACCENT, relief="flat", bd=0)
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    inner = tk.Frame(canvas, bg=BG2)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.columnconfigure(0, weight=1)

    def _resize(e):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(win_id, width=canvas.winfo_width())
    inner.bind("<Configure>", _resize)
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

    # Mouse-wheel scrolling
    def _wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _wheel)

    return canvas, inner


# ── Duplicate pair resolution (same logic as duplicate_reviewer.py) ──────────

def _resolve_path(raw: str, conn: sqlite3.Connection,
                  vault_root: Path) -> Path:
    p = Path(raw)
    if p.exists():
        return p
    row = conn.execute(
        "SELECT destination FROM photos WHERE original=? LIMIT 1", (raw,)
    ).fetchone()
    if row:
        rp = Path(row[0])
        if rp.exists():
            return rp
    row = conn.execute(
        "SELECT destination FROM integrity WHERE source=? LIMIT 1", (raw,)
    ).fetchone()
    if row:
        rp = Path(row[0])
        if rp.exists():
            return rp
    fname = p.name.lower()
    for c in vault_root.rglob("*"):
        if c.name.lower() == fname and c.is_file():
            return c
    return p


def load_dup_pairs(db_path: Path, vault_root: Path) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, path, original, kind, action, kept
           FROM duplicates
           WHERE action NOT IN (
               'reviewed-keep-original',
               'reviewed-keep-duplicate',
               'reviewed-keep-both'
           )
           ORDER BY id"""
    ).fetchall()
    pairs = []
    for row in rows:
        d = dict(row)
        d["path_resolved"]     = _resolve_path(d["path"],     conn, vault_root)
        d["original_resolved"] = _resolve_path(d["original"], conn, vault_root)
        pairs.append(d)
    conn.close()
    return pairs


def mark_reviewed(db_path: Path, dup_id: int, action: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE duplicates SET action=? WHERE id=?", (action, dup_id))
    conn.commit()
    conn.close()


# ── Main application ──────────────────────────────────────────────────────────

class PhotoOrganizerApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.configure(bg=BG)
        self._go_fullscreen()

        # ── i18n — detect OS language before building any widget ─────────
        detected = detect_language()
        set_language(detected)
        self.v_language = tk.StringVar(value=detected)
        self.title(t("app_title"))

        # ── State ────────────────────────────────────────────────────────
        self.v_input       = tk.StringVar()
        self.v_output      = tk.StringVar()
        self.v_vault       = tk.StringVar()
        self.v_notes       = tk.StringVar()
        self.v_dry_run     = tk.BooleanVar(value=True)
        self.v_skip_ai     = tk.BooleanVar(value=False)
        self.v_skip_faces  = tk.BooleanVar(value=False)
        self.v_skip_video  = tk.BooleanVar(value=False)
        self.v_skip_phash  = tk.BooleanVar(value=False)
        self.v_dup_report  = tk.BooleanVar(value=True)
        self.v_dup_action  = tk.StringVar(value="skip")
        self.v_threshold   = tk.IntVar(value=8)
        self.v_no_integrity = tk.BooleanVar(value=False)
        self.v_io_workers   = tk.IntVar(value=0)
        self.v_ai_workers   = tk.IntVar(value=0)

        self._process      = None
        self._log_queue    = queue.Queue()
        self._running      = False
        self._dup_pairs    = []
        self._dup_idx      = 0
        self._dup_thumbs   = []
        self._dup_history  = []

        # ── Progress bar state ───────────────────────────────────────────
        self._progress_total   = 0     # total files (parsed from "Found N")
        self._progress_current = 0     # files completed so far
        self._progress_var     = tk.DoubleVar(value=0.0)
        self._progress_mode    = "idle"  # idle | indeterminate | determinate

        # ── i18n: dict of (widget, attr, key, kwargs_fn) for retranslation
        self._i18n_widgets: list[tuple] = []

        self._build_ui()
        self._load_prefs()
        self.after(80, self._poll_log)

        # Register hot-reload callback AFTER widgets are built
        on_language_change(self._retranslate)

        self.bind("<Escape>", lambda _: self._toggle_fullscreen())
        self.bind("<F11>",    lambda _: self._toggle_fullscreen())

    # ── i18n helpers ──────────────────────────────────────────────────────

    def _reg(self, widget, attr: str, key: str, **kw) -> None:
        """Register a widget for hot-reload retranslation."""
        self._i18n_widgets.append((widget, attr, key, kw))

    def _retranslate(self, _code: str = "") -> None:
        """Called by i18n on every set_language() — updates all registered widgets."""
        self.title(t("app_title"))
        for widget, attr, key, kw in self._i18n_widgets:
            try:
                val = t(key, **kw) if kw else t(key)
                if isinstance(widget, tk.StringVar):
                    widget.set(val)
                else:
                    widget.config(**{attr: val})
            except Exception:
                pass

    # ── Fullscreen ────────────────────────────────────────────────────────

    def _go_fullscreen(self):
        try:
            self.state("zoomed")          # Windows / most Linux WMs
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)   # some Linux
            except tk.TclError:
                self.attributes("-fullscreen", True)  # macOS fallback

    def _toggle_fullscreen(self):
        try:
            cur = self.state()
            self.state("normal" if cur == "zoomed" else "zoomed")
        except tk.TclError:
            pass

    # ── Top-level layout ──────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_right_panel()
        # Show resolved Python in log on startup
        self.after(200, lambda: self._log_write(
            f"Python: {PYTHON}", "dim"))

    # ─────────────────────────────────────────────────────────────────────
    # LEFT SIDEBAR
    # ─────────────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=BG2, width=SIDEBAR_W)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.pack_propagate(False)
        sidebar.grid_propagate(False)

        # Header
        hdr = tk.Frame(sidebar, bg=BG2)
        hdr.grid(row=0, column=0, sticky="ew", pady=(18, 4))
        tk.Label(hdr, text="Photo Organizer", bg=BG2, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=16)
        tk.Label(hdr, text="+ Obsidian", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 10)).pack(side="left")

        # Scrollable area
        scroll_wrap = tk.Frame(sidebar, bg=BG2)
        scroll_wrap.grid(row=1, column=0, sticky="nsew")
        sidebar.rowconfigure(1, weight=1)
        _, inner = _scrollable_frame(scroll_wrap)
        self._populate_sidebar(inner)

        # Run button pinned at bottom
        self._run_btn = tk.Button(
            sidebar, text="Run",
            command=self._on_run,
            bg=ACCENT, fg="#fff", relief="flat", bd=0,
            font=("Segoe UI", 11, "bold"), cursor="hand2",
            activebackground="#6657d4", pady=14,
        )
        self._run_btn.grid(row=2, column=0, sticky="ew", padx=16, pady=12)

    def _populate_sidebar(self, p):
        row = 0
        import os as _os
        cpu = _os.cpu_count() or 4

        def _sec(key):
            lbl = tk.Label(p, text=t(key), bg=BG2, fg=ACCENT,
                           font=("Segoe UI", 7, "bold"), anchor="w")
            lbl.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(14,2))
            self._reg(lbl, "text", key)

        def _field_label(key):
            lbl = tk.Label(p, text=t(key), bg=BG2, fg=FG2,
                           font=("Segoe UI", 9), anchor="w")
            lbl.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(4,0))
            self._reg(lbl, "text", key)

        def _chk(key, var):
            cb = tk.Checkbutton(p, text=t(key), variable=var,
                                bg=BG2, fg=FG2, selectcolor=BG3,
                                activebackground=BG2, activeforeground=FG,
                                font=("Segoe UI", 9), highlightthickness=0,
                                bd=0, cursor="hand2")
            cb.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=2)
            self._reg(cb, "text", key)

        # Folders
        _sec("section_folders"); row += 1
        for key, var in [
            ("lbl_source_folder", self.v_input),
            ("lbl_output_folder", self.v_output),
            ("lbl_vault_folder",  self.v_vault),
            ("lbl_notes_folder",  self.v_notes),
        ]:
            _field_label(key); row += 1
            _browse_row(p, var, row, t(key)); row += 1

        _separator(p, row); row += 1

        # Options
        _sec("section_options"); row += 1
        for key, var in [
            ("chk_dry_run",    self.v_dry_run),
            ("chk_skip_ai",    self.v_skip_ai),
            ("chk_skip_faces", self.v_skip_faces),
            ("chk_skip_video", self.v_skip_video),
        ]:
            _chk(key, var); row += 1

        _separator(p, row); row += 1

        # Duplicates
        _sec("section_duplicates"); row += 1
        _field_label("lbl_dup_action"); row += 1
        pill_row = tk.Frame(p, bg=BG2)
        pill_row.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(2,6)); row += 1
        for val, key, active_bg in [
            ("skip",  "dup_log_only", ACCENT),
            ("move",  "dup_move",     ACCENT2),
            ("trash", "dup_delete",   DANGER),
        ]:
            rb = tk.Radiobutton(pill_row, text=t(key),
                                variable=self.v_dup_action, value=val,
                                bg=BG2, fg=FG, selectcolor=active_bg,
                                activebackground=BG2, activeforeground=FG,
                                font=("Segoe UI", 9), highlightthickness=0,
                                bd=0, cursor="hand2", indicatoron=0,
                                relief="flat", padx=8, pady=5)
            rb.pack(side="left", padx=(0, 4))
            self._reg(rb, "text", key)
        for key, var in [("chk_dup_report", self.v_dup_report),
                         ("chk_skip_phash", self.v_skip_phash)]:
            _chk(key, var); row += 1
        _field_label("lbl_phash_threshold"); row += 1
        thr_f = tk.Frame(p, bg=BG2)
        thr_f.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0,4)); row += 1
        thr_f.columnconfigure(0, weight=1)
        tk.Scale(thr_f, from_=0, to=20, variable=self.v_threshold,
                 orient="horizontal", bg=BG2, fg=FG2, troughcolor=BG3,
                 highlightthickness=0, bd=0, sliderrelief="flat",
                 activebackground=ACCENT, font=("Segoe UI", 8), showvalue=True
                 ).grid(row=0, column=0, sticky="ew")
        hint_l = tk.Label(thr_f, text=t("phash_hint"), bg=BG2, fg=FG3, font=("Segoe UI", 8))
        hint_l.grid(row=1, column=0, sticky="w")
        self._reg(hint_l, "text", "phash_hint")

        _separator(p, row); row += 1

        # Integrity
        _sec("section_integrity"); row += 1
        int_desc = tk.Label(p, text=t("integrity_desc"), bg=BG2, fg=FG3,
                            font=("Segoe UI", 8), justify="left")
        int_desc.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(2,6))
        self._reg(int_desc, "text", "integrity_desc"); row += 1
        _chk("chk_no_integrity", self.v_no_integrity); row += 1
        int_f = tk.Frame(p, bg=BG2)
        int_f.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4,8)); row += 1
        self._integrity_dot = tk.Label(int_f, text="*", bg=BG2, fg=FG3, font=("Segoe UI", 11))
        self._integrity_dot.pack(side="left", padx=(0, 6))
        self._integrity_status = tk.Label(int_f, text=t("integrity_pending"),
                                           bg=BG2, fg=FG3, font=("Segoe UI", 9))
        self._integrity_status.pack(side="left")
        self._reg(self._integrity_status, "text", "integrity_pending")

        _separator(p, row); row += 1

        # Workers
        _sec("section_workers"); row += 1

        def _worker_row(key: str, var: tk.IntVar, r: int, max_val: int) -> None:
            lbl = tk.Label(p, text=t(key), bg=BG2, fg=FG2, font=("Segoe UI", 9), anchor="w")
            lbl.grid(row=r, column=0, columnspan=2, sticky="w", padx=16, pady=(4,0))
            self._reg(lbl, "text", key)
            f = tk.Frame(p, bg=BG2)
            f.grid(row=r+1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0,4))
            f.columnconfigure(0, weight=1)
            val_lbl = tk.Label(f, text=t("workers_auto"), bg=BG2, fg=FG3,
                               font=("Segoe UI", 8), width=6, anchor="e")
            val_lbl.grid(row=0, column=1, padx=(6,0))
            self._reg(val_lbl, "text", "workers_auto")
            def _upd(v, lbl=val_lbl):
                iv = int(float(v))
                lbl.config(text=t("workers_auto") if iv == 0 else str(iv))
            tk.Scale(f, from_=0, to=max_val, variable=var,
                     orient="horizontal", bg=BG2, fg=FG2, troughcolor=BG3,
                     highlightthickness=0, bd=0, sliderrelief="flat",
                     activebackground=ACCENT, font=("Segoe UI", 8),
                     showvalue=False, command=_upd
                     ).grid(row=0, column=0, sticky="ew")
            hint_w = tk.Label(f, text=t("workers_hint"), bg=BG2, fg=FG3, font=("Segoe UI", 7))
            hint_w.grid(row=1, column=0, columnspan=2, sticky="w")
            self._reg(hint_w, "text", "workers_hint")

        _worker_row("lbl_io_workers", self.v_io_workers, row, cpu * 2); row += 2
        _worker_row("lbl_ai_workers", self.v_ai_workers, row, cpu);     row += 2

        _separator(p, row); row += 1

        # Maintenance
        _sec("section_maintenance"); row += 1
        for btn_key, hint_key, cmd in [
            ("btn_review_dupes",  "review_dupes_hint",  self._show_reviewer_tab),
            ("btn_edit_faces",    "edit_faces_hint",    self._show_faces_tab),
            ("btn_cleanup_notes", "cleanup_notes_hint", self._on_cleanup_notes),
        ]:
            is_accent = btn_key in ("btn_review_dupes", "btn_edit_faces")
            b = tk.Button(p, text=t(btn_key), command=cmd,
                          bg=ACCENT if is_accent else BG3,
                          fg="#fff" if is_accent else FG2,
                          relief="flat", bd=0,
                          font=("Segoe UI", 9, "bold" if is_accent else "normal"),
                          cursor="hand2",
                          activebackground="#6657d4" if is_accent else BORDER,
                          padx=10, pady=8)
            b.grid(row=row, column=0, columnspan=2,
                   sticky="ew" if is_accent else "w", padx=16, pady=(2,2))
            self._reg(b, "text", btn_key); row += 1
            h = tk.Label(p, text=t(hint_key), bg=BG2, fg=FG3, font=("Segoe UI", 8))
            h.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(0,8))
            self._reg(h, "text", hint_key); row += 1

        _separator(p, row); row += 1

        # Language selector
        _sec("section_language"); row += 1
        _field_label("lbl_language"); row += 1
        langs       = available_languages()
        lang_codes  = [l["code"] for l in langs]
        lang_labels = [l["lang"] for l in langs]
        cur_label   = next((l["lang"] for l in langs
                            if l["code"] == self.v_language.get()), lang_labels[0])
        self._lang_combo_var = tk.StringVar(value=cur_label)
        combo = ttk.Combobox(p, textvariable=self._lang_combo_var,
                             values=lang_labels, state="readonly",
                             font=("Segoe UI", 9))
        combo.grid(row=row, column=0, columnspan=2, sticky="ew",
                   padx=16, pady=(2,12), ipady=3); row += 1
        def _on_lang(e):
            idx  = lang_labels.index(self._lang_combo_var.get())
            code = lang_codes[idx]
            self.v_language.set(code)
            set_language(code)
            self._save_prefs()
        combo.bind("<<ComboboxSelected>>", _on_lang)

    # ─────────────────────────────────────────────────────────────────────
    # RIGHT PANEL (tabbed)
    # ─────────────────────────────────────────────────────────────────────

    def _build_right_panel(self):
        right = tk.Frame(self, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        # Tab bar
        tab_bar = tk.Frame(right, bg=BG2, height=42)
        tab_bar.grid(row=0, column=0, sticky="ew")
        tab_bar.columnconfigure(3, weight=1)  # spacer

        self._tab_btns: dict[str, tk.Button] = {}
        self._tab_frames: dict[str, tk.Frame] = {}
        self._active_tab = tk.StringVar(value="logs")

        for i, (key, label) in enumerate([
            ("logs",    "Logs"),
            ("review",  "Review Duplicates"),
            ("faces",   "Face Labels"),
        ]):
            b = tk.Button(
                tab_bar, text=label,
                command=lambda k=key: self._switch_tab(k),
                bg=BG2, fg=FG2, relief="flat", bd=0,
                font=("Segoe UI", 9), cursor="hand2",
                activebackground=BG3, activeforeground=FG,
                padx=18, pady=10,
            )
            b.grid(row=0, column=i, sticky="ns")
            self._tab_btns[key] = b

        # Content area
        content = tk.Frame(right, bg=BG)
        content.grid(row=1, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self._tab_frames["logs"]   = self._build_logs_tab(content)
        self._tab_frames["review"] = self._build_review_tab(content)
        self._tab_frames["faces"]  = self._build_faces_tab(content)

        for frame in self._tab_frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

        self._switch_tab("logs")

    def _switch_tab(self, key: str):
        self._active_tab.set(key)
        for k, btn in self._tab_btns.items():
            active = (k == key)
            btn.config(
                bg=BG3 if active else BG2,
                fg=FG  if active else FG2,
                font=("Segoe UI", 9, "bold" if active else "normal"),
            )
        self._tab_frames[key].tkraise()
        if key == "review":
            self._load_dup_pairs()
        elif key == "faces":
            self._load_face_labels()

    def _show_reviewer_tab(self):
        self._switch_tab("review")

    def _show_faces_tab(self):
        self._switch_tab("faces")

    # ── Logs tab ──────────────────────────────────────────────────────────

    def _build_logs_tab(self, parent: tk.Frame) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        frame.rowconfigure(2, weight=1)   # row 2 = log text (grows)
        frame.columnconfigure(0, weight=1)

        # ── Header bar ────────────────────────────────────────────────────
        bar = tk.Frame(frame, bg=BG2, height=46)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)

        self._status_dot = tk.Label(bar, text="●", bg=BG2, fg=FG3,
                                     font=("Segoe UI", 11))
        self._status_dot.grid(row=0, column=0, padx=(16, 6), pady=12)

        self._status_lbl = tk.Label(bar, text=t("status_ready"), bg=BG2, fg=FG2,
                                     font=("Segoe UI", 9))
        self._status_lbl.grid(row=0, column=1, sticky="w")
        self._reg(self._status_lbl, "text", "status_ready")

        clear_btn = tk.Button(bar, text=t("btn_clear"), command=self._clear_log,
                  bg=BG2, fg=FG3, relief="flat", bd=0,
                  font=("Segoe UI", 8), cursor="hand2",
                  activebackground=BG3, padx=10, pady=6)
        clear_btn.grid(row=0, column=2, padx=8, pady=6)
        self._reg(clear_btn, "text", "btn_clear")

        # ── Progress bar ──────────────────────────────────────────────────
        prog_frame = tk.Frame(frame, bg=BG2)
        prog_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        prog_frame.columnconfigure(1, weight=1)

        self._prog_lbl = tk.Label(prog_frame, text=t("progress_idle"),
                                   bg=BG2, fg=FG3,
                                   font=("Segoe UI", 8), width=22, anchor="w")
        self._prog_lbl.grid(row=0, column=0, padx=(16, 8), pady=6)

        # Custom styled progress bar using ttk
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Org.Horizontal.TProgressbar",
                        troughcolor=BG3,
                        background=ACCENT,
                        bordercolor=BG2,
                        lightcolor=ACCENT,
                        darkcolor=ACCENT)
        self._progress_bar = ttk.Progressbar(
            prog_frame,
            variable=self._progress_var,
            style="Org.Horizontal.TProgressbar",
            mode="determinate",
            maximum=100,
        )
        self._progress_bar.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=6)

        self._prog_pct = tk.Label(prog_frame, text="", bg=BG2, fg=FG2,
                                   font=("Segoe UI", 8), width=6, anchor="e")
        self._prog_pct.grid(row=0, column=2, padx=(0, 16))

        # ── Log text ──────────────────────────────────────────────────────
        log_wrap = tk.Frame(frame, bg=BG)
        log_wrap.grid(row=2, column=0, sticky="nsew")
        log_wrap.rowconfigure(0, weight=1)
        log_wrap.columnconfigure(0, weight=1)

        self._log = tk.Text(
            log_wrap, bg=BG, fg=FG, insertbackground=FG,
            font=(MONO, 9), relief="flat", bd=0,
            wrap="word", state="disabled", selectbackground=ACCENT,
        )
        log_sb = tk.Scrollbar(log_wrap, orient="vertical",
                               command=self._log.yview,
                               bg=BG3, troughcolor=BG, width=14,
                               activebackground=ACCENT, relief="flat", bd=0)
        self._log.configure(yscrollcommand=log_sb.set)
        self._log.grid(row=0, column=0, sticky="nsew")
        log_sb.grid(row=0, column=1, sticky="ns")

        for tag, color, bold in [
            ("info",    FG,       False),
            ("ok",      ACCENT2,  False),
            ("warn",    WARN,     False),
            ("err",     DANGER,   False),
            ("dup",     DUP_C,    False),
            ("section", ACCENT,   True),
            ("video",   VID_C,    False),
            ("dim",     FG3,      False),
        ]:
            kw = {"foreground": color}
            if bold:
                kw["font"] = (MONO, 9, "bold")
            self._log.tag_config(tag, **kw)

        # ── Stats footer ──────────────────────────────────────────────────
        footer = tk.Frame(frame, bg=BG2, height=32)
        footer.grid(row=3, column=0, sticky="ew")
        self._stats_lbl = tk.Label(footer, text="", bg=BG2, fg=FG3,
                                    font=("Segoe UI", 8))
        self._stats_lbl.pack(side="left", padx=16)

        return frame

    def _log_write(self, text: str, tag: str = "info"):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._stats_lbl.config(text="")
        self._reset_progress()

    def _reset_progress(self):
        """Reset progress bar to idle state."""
        self._progress_total   = 0
        self._progress_current = 0
        self._progress_var.set(0.0)
        self._progress_bar.config(mode="determinate")
        self._prog_lbl.config(text=t("progress_idle"), fg=FG3)
        self._prog_pct.config(text="")

    def _set_progress_indeterminate(self, label_key: str = "progress_loading"):
        """Switch to indeterminate (spinner) mode — used while CLIP loads."""
        self._progress_bar.config(mode="indeterminate")
        self._progress_bar.start(12)   # step every 12 ms
        self._prog_lbl.config(text=t(label_key), fg=WARN)
        self._prog_pct.config(text="")

    def _set_progress_determinate(self, current: int, total: int,
                                   label_key: str = "progress_scanning"):
        """Update determinate progress bar."""
        self._progress_bar.config(mode="determinate")
        self._progress_bar.stop()
        self._progress_total   = total
        self._progress_current = current
        pct = (current / total * 100) if total > 0 else 0
        self._progress_var.set(pct)
        self._prog_lbl.config(
            text=f"{t(label_key)}  {current}/{total}",
            fg=ACCENT2 if pct >= 100 else FG2,
        )
        self._prog_pct.config(text=f"{pct:.0f}%")

    def _finish_progress(self):
        """Mark progress as complete."""
        self._progress_bar.config(mode="determinate")
        self._progress_bar.stop()
        self._progress_var.set(100.0)
        self._prog_lbl.config(text=t("progress_done"), fg=ACCENT2)
        self._prog_pct.config(text="100%")

    def _poll_log(self):
        try:
            while True:
                line, tag = self._log_queue.get_nowait()
                self._log_write(line, tag)
        except queue.Empty:
            pass
        self.after(80, self._poll_log)

    # ── Review duplicates tab ─────────────────────────────────────────────

    def _build_review_tab(self, parent: tk.Frame) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        # ── Counter / badge bar ───────────────────────────────────────────
        top = tk.Frame(frame, bg=BG2, height=46)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(2, weight=1)

        self._dup_counter = tk.Label(top, text="", bg=BG2, fg=FG2,
                                      font=("Segoe UI", 9))
        self._dup_counter.grid(row=0, column=0, padx=(16, 8), pady=12)

        self._dup_badge = tk.Label(top, text="", bg=BG2, fg=FG3,
                                    font=("Segoe UI", 9))
        self._dup_badge.grid(row=0, column=1, sticky="w")

        # spacer
        tk.Frame(top, bg=BG2).grid(row=0, column=2, sticky="ew")

        tk.Button(top, text="Reload", command=self._load_dup_pairs,
                  bg=BG2, fg=FG3, relief="flat", bd=0,
                  font=("Segoe UI", 8), cursor="hand2",
                  activebackground=BG3, padx=10, pady=6
                  ).grid(row=0, column=3, padx=(0, 8), pady=6)

        # ── Photo panels (fill all available space) ───────────────────────
        self._dup_left  = self._photo_panel(frame, "Original",  row=1, col=0)
        self._dup_right = self._photo_panel(frame, "Duplicate", row=1, col=1)

        # ── Action buttons ────────────────────────────────────────────────
        btn_f = tk.Frame(frame, bg=BG2)
        btn_f.grid(row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        btn_f.columnconfigure(4, weight=1)   # spacer pushes back btn right

        self._dup_btn_left = tk.Button(
            btn_f, text="← Keep original",
            command=self._dup_keep_left,
            bg=ACCENT2, fg="#fff", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            activebackground="#3aaa85", padx=20, pady=12,
        )
        self._dup_btn_left.grid(row=0, column=0, padx=(12, 4), pady=10)

        self._dup_btn_both = tk.Button(
            btn_f, text="Keep both",
            command=self._dup_keep_both,
            bg=BG3, fg=FG, relief="flat", bd=0,
            font=("Segoe UI", 10), cursor="hand2",
            activebackground=BORDER, padx=20, pady=12,
        )
        self._dup_btn_both.grid(row=0, column=1, padx=4, pady=10)

        self._dup_btn_right = tk.Button(
            btn_f, text="Keep duplicate →",
            command=self._dup_keep_right,
            bg=ACCENT, fg="#fff", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            activebackground="#6657d4", padx=20, pady=12,
        )
        self._dup_btn_right.grid(row=0, column=2, padx=4, pady=10)

        self._dup_btn_skip = tk.Button(
            btn_f, text="Skip",
            command=self._dup_skip,
            bg=BG3, fg=FG3, relief="flat", bd=0,
            font=("Segoe UI", 9), cursor="hand2",
            activebackground=BORDER, padx=14, pady=12,
        )
        self._dup_btn_skip.grid(row=0, column=3, padx=(18, 4), pady=10)

        # spacer column 4
        tk.Frame(btn_f, bg=BG2).grid(row=0, column=4, sticky="ew")

        self._dup_btn_back = tk.Button(
            btn_f, text="↩ Undo",
            command=self._dup_undo,
            bg=BG3, fg=FG3, relief="flat", bd=0,
            font=("Segoe UI", 9), cursor="hand2",
            activebackground=BORDER, padx=14, pady=12,
            state="disabled",
        )
        self._dup_btn_back.grid(row=0, column=5, padx=(4, 12), pady=10)

        # ── Key bindings ──────────────────────────────────────────────────
        def _only_review(fn):
            return lambda e: fn() if self._active_tab.get() == "review" else None
        self.bind("<Left>",       _only_review(self._dup_keep_left))
        self.bind("<Right>",      _only_review(self._dup_keep_right))
        self.bind("<Up>",         _only_review(self._dup_keep_both))
        self.bind("<space>",      _only_review(self._dup_skip))
        self.bind("<BackSpace>",  _only_review(self._dup_undo))

        return frame

    def _photo_panel(self, parent: tk.Frame, role: str,
                     row: int, col: int) -> dict:
        frame = tk.Frame(parent, bg=BG2,
                         highlightthickness=2, highlightbackground=BORDER)
        frame.grid(row=row, column=col, sticky="nsew",
                   padx=(8 if col == 0 else 4, 4 if col == 0 else 8),
                   pady=4)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        tk.Label(frame, text=role, bg=BG2, fg=FG3,
                 font=("Segoe UI", 8, "bold"), anchor="center"
                 ).grid(row=0, column=0, sticky="ew", pady=(8, 0))

        # Canvas expands to fill all available space
        canvas = tk.Canvas(frame, bg=BG3, highlightthickness=0, bd=0)
        canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        meta = tk.Frame(frame, bg=BG2)
        meta.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 10))
        meta.columnconfigure(0, weight=1)

        name_l = tk.Label(meta, text="", bg=BG2, fg=FG,
                          font=("Segoe UI", 9, "bold"), anchor="w")
        name_l.grid(row=0, column=0, sticky="ew")
        info_l = tk.Label(meta, text="", bg=BG2, fg=FG2,
                          font=("Segoe UI", 8), anchor="w")
        info_l.grid(row=1, column=0, sticky="ew")
        path_l = tk.Label(meta, text="", bg=BG2, fg=FG3,
                          font=(MONO, 7), anchor="w")
        path_l.grid(row=2, column=0, sticky="ew")

        panel = {"frame": frame, "canvas": canvas,
                 "name": name_l, "info": info_l, "path": path_l,
                 "_pil_img": None}   # store the PIL Image for redraws

        # Redraw whenever the canvas is resized
        def _on_resize(event, p=panel):
            if p["_pil_img"] is not None:
                self._dup_redraw_canvas(p)
            # Update wraplength on meta labels
            w = max(event.width - 16, 50)
            p["name"].config(wraplength=w)
            p["path"].config(wraplength=w)

        canvas.bind("<Configure>", _on_resize)

        return panel

    # ── Duplicate logic ───────────────────────────────────────────────────

    def _load_dup_pairs(self):
        vlt = self.v_vault.get().strip()
        if not vlt:
            self._dup_counter.config(text="Set vault folder first")
            return
        db = Path(vlt) / "photo_organizer.db"
        self._dup_pairs   = load_dup_pairs(db, Path(vlt))
        self._dup_idx     = 0
        self._dup_history = []
        self._dup_btn_back.config(state="disabled")
        self._dup_render()

    def _dup_render(self):
        # Clear stale thumbnail references from previous pair
        self._dup_thumbs = []
        if not self._dup_pairs:
            self._dup_counter.config(text="No pairs to review")
            self._dup_badge.config(text="Run the organiser first, or all pairs already reviewed.", fg=FG3)
            for p in (self._dup_left, self._dup_right):
                p["canvas"].delete("all")
                p["canvas"].create_text(THUMB_W//2, THUMB_H//2,
                    text="Nothing to review", fill=FG3,
                    font=("Segoe UI", 11), justify="center")
                p["name"].config(text="", fg=FG)
                p["info"].config(text="")
                p["path"].config(text="")
            for b in (self._dup_btn_left, self._dup_btn_both,
                      self._dup_btn_right, self._dup_btn_skip):
                b.config(state="disabled")
            return

        if self._dup_idx >= len(self._dup_pairs):
            self._dup_counter.config(text=f"All {len(self._dup_pairs)} pair(s) reviewed [OK]")
            self._dup_badge.config(text="", fg=FG3)
            for p in (self._dup_left, self._dup_right):
                p["canvas"].delete("all")
                p["canvas"].create_text(THUMB_W//2, THUMB_H//2,
                    text="All done!", fill=ACCENT2,
                    font=("Segoe UI", 13, "bold"), justify="center")
                p["name"].config(text="", fg=FG)
                p["info"].config(text="")
                p["path"].config(text="")
            for b in (self._dup_btn_left, self._dup_btn_both,
                      self._dup_btn_right, self._dup_btn_skip):
                b.config(state="disabled")
            return

        for b in (self._dup_btn_left, self._dup_btn_both,
                  self._dup_btn_right, self._dup_btn_skip):
            b.config(state="normal")

        pair  = self._dup_pairs[self._dup_idx]
        left  = pair["original_resolved"]
        right = pair["path_resolved"]
        kind  = pair["kind"].upper()

        self._dup_counter.config(
            text=f"{self._dup_idx + 1} / {len(self._dup_pairs)}")
        self._dup_badge.config(
            text=f"{kind} duplicate  (id {pair['id']})",
            fg=DANGER if kind == "EXACT" else WARN)

        self._dup_fill_panel(self._dup_left,  left)
        self._dup_fill_panel(self._dup_right, right)
        self._dup_highlight_better(left, right)

    def _dup_redraw_canvas(self, panel: dict):
        """Redraw the stored PIL image scaled to the current canvas size."""
        canvas = panel["canvas"]
        pil    = panel["_pil_img"]
        if pil is None:
            return
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        try:
            from PIL import Image, ImageTk
            img = pil.copy()
            img.thumbnail((cw, ch), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self._dup_thumbs.append(tk_img)
            canvas.delete("all")
            canvas.create_image(cw // 2, ch // 2, anchor="center", image=tk_img)
        except Exception:
            pass

    def _dup_fill_panel(self, panel: dict, path: Path):
        canvas = panel["canvas"]
        canvas.delete("all")
        panel["_pil_img"] = None

        if not path.exists():
            canvas.create_text(
                canvas.winfo_width() // 2 or 200,
                canvas.winfo_height() // 2 or 150,
                text=f"Not found\n{path.name}",
                fill=DANGER, font=("Segoe UI", 10), justify="center",
            )
            panel["name"].config(text=path.name, fg=DANGER)
            panel["info"].config(text="MISSING — file could not be located")
            panel["path"].config(text=str(path))
            return

        def _bg():
            try:
                from PIL import Image
                img = Image.open(path).convert("RGB")
                # Store original for quality redraws on resize
                panel["_pil_img"] = img
                self.after(0, lambda: self._dup_redraw_canvas(panel))
            except Exception:
                self.after(0, lambda: canvas.create_text(
                    canvas.winfo_width() // 2 or 200,
                    canvas.winfo_height() // 2 or 150,
                    text="Preview unavailable",
                    fill=FG3, font=("Segoe UI", 10),
                ))

        threading.Thread(target=_bg, daemon=True).start()

        # Metadata (available immediately without opening image)
        try:
            from PIL import Image
            with Image.open(path) as img:
                w, h = img.width, img.height
        except Exception:
            w, h = 0, 0

        size = path.stat().st_size
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                break
            size /= 1024
        size_str = f"{size:.1f} {unit}"

        try:
            mtime = datetime.fromtimestamp(
                path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            mtime = "?"

        panel["name"].config(text=path.name, fg=FG)
        panel["info"].config(text=f"{w}×{h}  ·  {size_str}  ·  {mtime}")
        panel["path"].config(text=str(path.parent))

    def _dup_highlight_better(self, left: Path, right: Path):
        def px(p):
            try:
                from PIL import Image
                with Image.open(p) as img:
                    return img.width * img.height
            except Exception:
                return 0
        lp, rp = px(left), px(right)
        self._dup_left["frame"].config(
            highlightbackground=ACCENT2 if lp >= rp else BORDER)
        self._dup_right["frame"].config(
            highlightbackground=ACCENT2 if rp > lp else BORDER)

    def _dup_delete(self, path: Path, label: str) -> Path | None:
        """
        Move *path* to duplicates/reviewed/.
        Returns the destination path so the action can be undone,
        or None if nothing was moved (dry-run / file missing).
        """
        vlt = self.v_vault.get().strip()
        rev_dir = Path(vlt) / "duplicates" / "reviewed"

        if self.v_dry_run.get():
            self._log_write(f"[dry-run] would remove {label}: {path}", "warn")
            return None

        if not path.exists():
            return None

        try:
            rev_dir.mkdir(parents=True, exist_ok=True)
            dest = rev_dir / path.name
            c = 1
            while dest.exists():
                dest = rev_dir / f"{path.stem}_{c}{path.suffix}"
                c += 1
            shutil.move(str(path), dest)
            self._log_write(f"  moved {label} → {dest}", "ok")
            return dest
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return None

    def _dup_advance(self, action: str, deleted_src: Path | None = None,
                     deleted_dst: Path | None = None):
        pair = self._dup_pairs[self._dup_idx]
        vlt  = self.v_vault.get().strip()
        if vlt and not self.v_dry_run.get():
            mark_reviewed(Path(vlt) / "photo_organizer.db", pair["id"], action)

        # Push to history so undo can reverse it
        self._dup_history.append({
            "idx":         self._dup_idx,
            "action":      action,
            "pair_id":     pair["id"],
            "deleted_src": deleted_src,
            "deleted_dst": deleted_dst,
        })

        self._dup_idx += 1
        self._dup_render()
        self._dup_btn_back.config(state="normal")

    def _dup_undo(self):
        """Reverse the last decision: restore the moved file and go back one pair."""
        if not self._dup_history:
            return

        entry = self._dup_history.pop()

        # Restore the file that was moved to reviewed/
        src = entry["deleted_src"]
        dst = entry["deleted_dst"]
        if src and dst and Path(dst).exists():
            try:
                shutil.move(str(dst), str(src))
                self._log_write(f"  [undo] restored {Path(src).name}", "warn")
            except Exception as e:
                self._log_write(f"  [undo] could not restore file: {e}", "err")
        elif src and dst:
            self._log_write(f"  [undo] file already gone from reviewed/: {Path(dst).name}", "warn")

        # Revert DB action back to 'skip'
        vlt = self.v_vault.get().strip()
        if vlt and not self.v_dry_run.get():
            try:
                mark_reviewed(Path(vlt) / "photo_organizer.db",
                              entry["pair_id"], "skip")
            except Exception:
                pass

        # Go back to the pair
        self._dup_idx = entry["idx"]
        self._dup_render()

        # Disable back button when history is empty
        if not self._dup_history:
            self._dup_btn_back.config(state="disabled")

    def _dup_keep_left(self):
        dst = self._dup_delete(self._dup_pairs[self._dup_idx]["path_resolved"], "duplicate")
        self._dup_advance("reviewed-keep-original",
                          self._dup_pairs[self._dup_idx]["path_resolved"], dst)

    def _dup_keep_right(self):
        dst = self._dup_delete(self._dup_pairs[self._dup_idx]["original_resolved"], "original")
        self._dup_advance("reviewed-keep-duplicate",
                          self._dup_pairs[self._dup_idx]["original_resolved"], dst)

    def _dup_keep_both(self):
        self._dup_advance("reviewed-keep-both")

    def _dup_skip(self):
        self._dup_history.append({
            "idx": self._dup_idx, "action": "skip",
            "pair_id": self._dup_pairs[self._dup_idx]["id"],
            "deleted_src": None, "deleted_dst": None,
        })
        self._dup_idx += 1
        self._dup_render()
        self._dup_btn_back.config(state="normal")

    # ── Face labels tab ───────────────────────────────────────────────────

    def _build_faces_tab(self, parent: tk.Frame) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # Header bar
        hdr = tk.Frame(frame, bg=BG2, height=46)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        tk.Label(hdr, text="Rename face labels", bg=BG2, fg=FG,
                 font=("Segoe UI", 11, "bold")
                 ).grid(row=0, column=0, padx=16, pady=12)
        tk.Label(hdr, text="Edit right column · Save to apply",
                 bg=BG2, fg=FG3, font=("Segoe UI", 8)
                 ).grid(row=0, column=1, sticky="w")
        tk.Button(hdr, text="Reload", command=self._load_face_labels,
                  bg=BG2, fg=FG3, relief="flat", bd=0,
                  font=("Segoe UI", 8), cursor="hand2",
                  activebackground=BG3, padx=10, pady=6
                  ).grid(row=0, column=2, padx=4, pady=6)

        # Scrollable label grid
        scroll_wrap = tk.Frame(frame, bg=BG)
        scroll_wrap.grid(row=1, column=0, sticky="nsew")
        _, self._faces_inner = _scrollable_frame(scroll_wrap)
        self._faces_inner.columnconfigure(1, weight=1)
        self._face_entries: list[tuple[str, tk.StringVar]] = []

        # Action buttons
        btn_f = tk.Frame(frame, bg=BG2)
        btn_f.grid(row=2, column=0, sticky="ew", padx=16, pady=12)

        tk.Button(btn_f, text="Save + apply to notes",
                  command=self._faces_save_apply,
                  bg=ACCENT, fg="#fff", relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  activebackground="#6657d4", padx=14, pady=8
                  ).pack(side="left", padx=(0, 8))
        tk.Button(btn_f, text="Save only",
                  command=self._faces_save_only,
                  bg=BG3, fg=FG2, relief="flat", bd=0,
                  font=("Segoe UI", 9), cursor="hand2",
                  activebackground=BORDER, padx=14, pady=8
                  ).pack(side="left")

        self._faces_status = tk.Label(btn_f, text="", bg=BG2, fg=ACCENT2,
                                       font=("Segoe UI", 9))
        self._faces_status.pack(side="left", padx=16)

        return frame

    def _load_face_labels(self):
        vlt = self.v_vault.get().strip()
        if not vlt:
            return
        labels_file = Path(vlt) / "face_labels.json"

        # Clear existing rows
        for w in self._faces_inner.winfo_children():
            w.destroy()
        self._face_entries.clear()

        if not labels_file.exists():
            tk.Label(self._faces_inner,
                     text="No face_labels.json found.\nRun the organiser first.",
                     bg=BG2, fg=FG3, font=("Segoe UI", 10), justify="center"
                     ).grid(row=0, column=0, columnspan=2, pady=40)
            return

        try:
            labels: dict = json.loads(labels_file.read_text(encoding="utf-8"))
        except Exception as e:
            tk.Label(self._faces_inner, text=f"Error: {e}",
                     bg=BG2, fg=DANGER, font=("Segoe UI", 9)
                     ).grid(row=0, column=0, columnspan=2, pady=20)
            return

        # Column headers
        tk.Label(self._faces_inner, text="Auto label", bg=BG2, fg=FG3,
                 font=("Segoe UI", 8, "bold"), anchor="w"
                 ).grid(row=0, column=0, sticky="w", padx=(16,8), pady=(12,4))
        tk.Label(self._faces_inner, text="Your name", bg=BG2, fg=FG3,
                 font=("Segoe UI", 8, "bold"), anchor="w"
                 ).grid(row=0, column=1, sticky="w", padx=(0,16), pady=(12,4))

        for i, (auto, human) in enumerate(sorted(labels.items()), start=1):
            tk.Label(self._faces_inner, text=auto, bg=BG2, fg=FG2,
                     font=(MONO, 9), anchor="w"
                     ).grid(row=i, column=0, sticky="w", padx=(16,8), pady=3)
            var = tk.StringVar(value=human)
            tk.Entry(self._faces_inner, textvariable=var,
                     bg=BG3, fg=FG, insertbackground=FG,
                     relief="flat", bd=0, font=("Segoe UI", 9),
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT
                     ).grid(row=i, column=1, sticky="ew", padx=(0,16),
                            pady=3, ipady=4)
            self._face_entries.append((auto, var))

        self._faces_status.config(text=f"{len(labels)} label(s) loaded")

    def _faces_save(self) -> tuple[Path | None, dict | None]:
        vlt = self.v_vault.get().strip()
        if not vlt:
            messagebox.showerror("Missing vault", "Set the vault folder first.")
            return None, None
        if not self._face_entries:
            messagebox.showinfo("Empty", "No labels to save.")
            return None, None
        labels_file = Path(vlt) / "face_labels.json"
        updated = {auto: var.get().strip() or auto
                   for auto, var in self._face_entries}
        labels_file.write_text(json.dumps(updated, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        return labels_file, updated

    def _faces_save_only(self):
        lf, _ = self._faces_save()
        if lf:
            self._faces_status.config(text="Saved [OK]", fg=ACCENT2)

    def _faces_save_apply(self):
        lf, _ = self._faces_save()
        if not lf:
            return
        self._faces_status.config(text="Applying…", fg=WARN)
        vlt   = self.v_vault.get().strip()
        notes = self.v_notes.get().strip() or str(Path(vlt) / "photo-notes")
        args  = [PYTHON, "photo_organizer.py",
                 "--vault", vlt, "--notes", notes, "--rename-faces"]
        self._switch_tab("logs")
        self._clear_log()
        self._log_write("Applying face renames…", "section")
        self._set_running(True)
        threading.Thread(target=self._run_process, args=(args,), daemon=True).start()

    # ── Run / process ─────────────────────────────────────────────────────

    def _set_running(self, running: bool):
        self._running = running
        if running:
            self._run_btn.config(text=t("btn_stop"), bg=DANGER,
                                 command=self._on_stop)
            self._status_dot.config(fg=ACCENT2)
            self._status_lbl.config(text=t("status_running"))
            self._set_progress_indeterminate("progress_loading")
        else:
            self._run_btn.config(text=t("btn_run"), bg=ACCENT,
                                 command=self._on_run)
            self._status_dot.config(fg=FG3)
            self._status_lbl.config(text=t("status_ready"))

    def _on_stop(self):
        if self._process:
            self._process.terminate()
            self._log_write(t("status_stopped"), "warn")
        self._set_running(False)
        self._finish_progress()

    def _build_args(self) -> list[str]:
        inp = self.v_input.get().strip()
        out = self.v_output.get().strip()
        vlt = self.v_vault.get().strip()
        if not inp or not out or not vlt:
            raise ValueError("Input, output, and vault folders are required.")
        args = [PYTHON, "photo_organizer.py",
                "--input", inp, "--output", out, "--vault", vlt]
        notes = self.v_notes.get().strip()
        if notes:
            args += ["--notes", notes]
        if self.v_dry_run.get():    args.append("--dry-run")
        if self.v_skip_ai.get():   args.append("--skip-ai")
        if self.v_skip_faces.get():args.append("--skip-faces")
        if self.v_skip_video.get():args.append("--skip-video")
        if self.v_skip_phash.get():args.append("--skip-phash")
        if self.v_dup_report.get():args.append("--dup-report")
        if self.v_no_integrity.get(): args.append("--no-integrity-report")
        io_w = self.v_io_workers.get()
        ai_w = self.v_ai_workers.get()
        if io_w > 0: args += ["--io-workers", str(io_w)]
        if ai_w > 0: args += ["--ai-workers", str(ai_w)]
        args += ["--dup-action", self.v_dup_action.get()]
        args += ["--phash-threshold",  str(self.v_threshold.get())]
        return args

    def _on_run(self):
        if self._running:
            return
        try:
            args = self._build_args()
        except ValueError as e:
            messagebox.showerror("Missing fields", str(e))
            return
        if self.v_dup_action.get() == "trash" and not self.v_dry_run.get():
            if not messagebox.askyesno("Confirm deletion",
                    "Duplicates will be permanently deleted.\n\nContinue?"):
                return
        self._switch_tab("logs")
        self._clear_log()
        self._log_write("$ " + " ".join(args), "dim")
        self._log_write("", "dim")
        self._set_running(True)
        self._save_prefs()
        threading.Thread(target=self._run_process, args=(args,), daemon=True).start()

    def _run_process(self, args: list[str]):
        # Suppress known harmless warnings at the subprocess level
        env = os.environ.copy()
        env["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
        env["TOKENIZERS_PARALLELISM"]            = "false"
        env["HF_HUB_DISABLE_SYMLINKS_WARNING"]   = "1"
        # Suppress Python DeprecationWarnings from third-party libs
        env["PYTHONWARNINGS"]  = "ignore::DeprecationWarning,ignore::UserWarning"
        env["PYTHONIOENCODING"] = "utf-8"  # force UTF-8 output on Windows

        # Lines that are safe to suppress entirely (never on in the UI)
        _NOISE: tuple[str, ...] = (
            "huggingface_hub",
            "hf_hub_disable_symlinks",
            "symlinks",
            "developer mode",
            "pkg_resources",
            "setuptools",
            "warnings.warn",
            "hf_token",
            "unauthenticated requests",
            "rate limit",
            "position_ids",
            "unexpected",
            "loading weights:",
            "load report",
            "key        ",
            "----------",
            "| status",
            "vision_model",
            "text_model",
            "notes:",
            "can be ignored",
            "userwarning:",
            "from pkg_resources",
        )

        try:
            self._process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=Path(__file__).parent,
                env=env,
            )
            photos = moved = dups = errors = integrity_ok = integrity_problems = 0
            total_files = 0   # parsed from "Found N photo(s) and M video(s)"

            import re as _re

            for raw in self._process.stdout:
                line  = raw.rstrip()
                lower = line.lower()

                # Drop known noise lines silently
                if any(n in lower for n in _NOISE):
                    continue

                # ── Progress: detect total from "Found N photo(s) and M video(s)" ──
                m_total = _re.search(r"found\s+(\d+)\s+photo.*?(\d+)\s+video", lower)
                if m_total:
                    total_files = int(m_total.group(1)) + int(m_total.group(2))
                    self.after(0, lambda tot=total_files:
                        self._set_progress_determinate(0, tot, "progress_scanning"))

                # ── Progress: detect current from "[X/N] filename" ──────────────
                m_cur = _re.match(r'^\[(\d+)/(\d+)\]', line)
                if m_cur:
                    cur = int(m_cur.group(1))
                    tot = int(m_cur.group(2))
                    if total_files == 0:
                        total_files = tot
                    self.after(0, lambda c=cur, tot=tot:
                        self._set_progress_determinate(c, tot, "progress_scanning"))

                # ── Progress: CLIP loading -> indeterminate ───────────────────────
                if "[ai] loading clip" in lower:
                    self.after(0, lambda:
                        self._set_progress_indeterminate("progress_loading"))

                # ── Progress: vault indexing ──────────────────────────────────────
                if "[index] pre-indexing vault" in lower:
                    self.after(0, lambda:
                        (self._prog_lbl.config(text="Indexing vault...", fg=WARN),
                         self._progress_bar.config(mode="indeterminate"),
                         self._progress_bar.start(12)))
                if "[index] done" in lower:
                    self.after(0, lambda:
                        (self._progress_bar.stop(),
                         self._progress_bar.config(mode="determinate"),
                         self._progress_var.set(0),
                         self._prog_lbl.config(text="Vault indexed — scanning...", fg=FG2)))

                tag = "info"

                if "[index]" in lower:
                    tag = "dim"
                elif "[integrity]" in lower:
                    if "[ok]" in lower:
                        tag = "ok";  integrity_ok += 1
                    elif "corrupted" in lower or "missing" in lower:
                        tag = "err"; integrity_problems += 1
                    else:
                        tag = "warn"
                elif "[video]" in lower:
                    tag = "warn" if "warning" in lower else "section"
                elif "[dup" in lower:
                    tag = "dup";  dups += 1
                elif "moved ->" in lower:
                    tag = "ok";   moved += 1
                elif "note  ->" in lower:
                    tag = "ok"
                elif "error" in lower or "traceback" in lower:
                    tag = "err";  errors += 1
                elif "warn" in lower or "[dry-run]" in lower:
                    tag = "warn"
                elif line.startswith("[") and "/" in line[:12]:
                    tag = "video" if "[video]" in line else "section"
                    photos += 1
                elif line.startswith("  "):
                    tag = "dim"

                self._log_queue.put((line, tag))

            self._process.wait()
            rc = self._process.returncode

            def _finish():
                if integrity_problems:
                    self._integrity_dot.config(fg=DANGER)
                    self._integrity_status.config(
                        text=f"{integrity_problems} problem(s) — check integrity_report.md",
                        fg=DANGER)
                elif integrity_ok:
                    self._integrity_dot.config(fg=ACCENT2)
                    self._integrity_status.config(
                        text=f"All {integrity_ok} file(s) OK", fg=ACCENT2)
                if rc == 0:
                    self._finish_progress()
                else:
                    self._reset_progress()

            self.after(0, _finish)
            self._log_queue.put(("", "info"))
            ok_mark  = "[OK]" if rc == 0 else "[!!]"
            summary  = (f"{ok_mark}  {photos} scanned - {moved} moved - "
                        f"{dups} dup(s) - {errors} error(s)")
            self._log_queue.put((summary, "ok" if rc == 0 else "err"))
            self.after(0, lambda: self._stats_lbl.config(text=summary))

        except FileNotFoundError:
            self._log_queue.put(("photo_organizer.py not found.", "err"))
        except Exception as e:
            self._log_queue.put((f"Error: {e}", "err"))
        finally:
            self.after(0, lambda: self._set_running(False))

    # ── Maintenance ───────────────────────────────────────────────────────

    def _on_cleanup_notes(self):
        vlt = self.v_vault.get().strip()
        if not vlt:
            messagebox.showerror(t("err_vault_missing"), t("err_vault_missing"))
            return
        dry = self.v_dry_run.get()
        if not dry and not messagebox.askyesno(
                t("confirm_cleanup_title"), t("confirm_cleanup_body")):
            return
        notes = self.v_notes.get().strip() or str(Path(vlt) / "photo-notes")
        args  = [PYTHON, "photo_organizer.py",
                 "--vault", vlt, "--notes", notes, "--cleanup-notes"]
        if dry:
            args.append("--dry-run")
        self._switch_tab("logs")
        self._clear_log()
        self._log_write(f"{'[dry-run] ' if dry else ''}Scanning for orphan notes...", "section")
        self._set_running(True)
        threading.Thread(target=self._run_process, args=(args,), daemon=True).start()

    # ── Preferences ───────────────────────────────────────────────────────

    def _prefs_path(self) -> Path:
        return Path(__file__).with_suffix(".prefs.json")

    def _save_prefs(self):
        try:
            self._prefs_path().write_text(json.dumps({
                "input":        self.v_input.get(),
                "output":       self.v_output.get(),
                "vault":        self.v_vault.get(),
                "notes":        self.v_notes.get(),
                "dry_run":      self.v_dry_run.get(),
                "skip_ai":      self.v_skip_ai.get(),
                "skip_faces":   self.v_skip_faces.get(),
                "skip_video":   self.v_skip_video.get(),
                "skip_phash":   self.v_skip_phash.get(),
                "dup_report":   self.v_dup_report.get(),
                "dup_action":   self.v_dup_action.get(),
                "threshold":    self.v_threshold.get(),
                "no_integrity": self.v_no_integrity.get(),
            "io_workers":   self.v_io_workers.get(),
            "ai_workers":   self.v_ai_workers.get(),
            "language":     self.v_language.get(),
            }, indent=2))
        except Exception:
            pass

    def _load_prefs(self):
        try:
            if not self._prefs_path().exists():
                return
            d = json.loads(self._prefs_path().read_text())
            self.v_input.set(d.get("input", ""))
            self.v_output.set(d.get("output", ""))
            self.v_vault.set(d.get("vault", ""))
            self.v_notes.set(d.get("notes", ""))
            self.v_dry_run.set(d.get("dry_run", True))
            self.v_skip_ai.set(d.get("skip_ai", False))
            self.v_skip_faces.set(d.get("skip_faces", False))
            self.v_skip_video.set(d.get("skip_video", False))
            self.v_skip_phash.set(d.get("skip_phash", False))
            self.v_dup_report.set(d.get("dup_report", True))
            self.v_dup_action.set(d.get("dup_action", "skip"))
            self.v_threshold.set(d.get("threshold", 8))
            self.v_no_integrity.set(d.get("no_integrity", False))
            self.v_io_workers.set(d.get("io_workers", 0))
            self.v_ai_workers.set(d.get("ai_workers", 0))
            saved_lang = d.get("language", "")
            if saved_lang and saved_lang != self.v_language.get():
                self.v_language.set(saved_lang)
                set_language(saved_lang)
        except Exception:
            pass

    def on_close(self):
        self._save_prefs()
        if self._process:
            self._process.terminate()
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = PhotoOrganizerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
