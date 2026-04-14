#!/usr/bin/env python3
"""
photo_organizer_ui.py
=====================
Desktop GUI for photo_organizer.py — no command line needed.
Requires: Python 3.10+ with Tkinter (included in standard installs).

Run:
    python photo_organizer_ui.py
"""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, messagebox, scrolledtext, ttk

# ── Palette ─────────────────────────────────────────────────────────────────
BG        = "#0f0f11"
BG2       = "#1a1a1f"
BG3       = "#25252d"
BORDER    = "#2e2e38"
ACCENT    = "#7c6af7"        # purple
ACCENT2   = "#5dcaa5"        # teal (success / active)
DANGER    = "#e05b5b"
FG        = "#e8e6f0"
FG2       = "#8e8ba0"
FG3       = "#5a5870"
MONO      = "Courier New"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _pick_dir(var: tk.StringVar, title: str = "Select folder"):
    path = filedialog.askdirectory(title=title)
    if path:
        var.set(path)


def _labeled_row(parent, label: str, row: int, col: int = 0,
                 colspan: int = 1, pady: int = 4) -> tk.Label:
    lbl = tk.Label(parent, text=label, bg=BG2, fg=FG2,
                   font=("Segoe UI", 9), anchor="w")
    lbl.grid(row=row, column=col, columnspan=colspan,
             sticky="w", padx=(16, 4), pady=(pady, 0))
    return lbl


def _entry(parent, textvariable, row: int, col: int = 0,
           colspan: int = 2, width: int = 38) -> tk.Entry:
    e = tk.Entry(parent, textvariable=textvariable,
                 bg=BG3, fg=FG, insertbackground=FG,
                 relief="flat", bd=0, font=("Segoe UI", 9),
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT, width=width)
    e.grid(row=row, column=col, columnspan=colspan,
           sticky="ew", padx=16, pady=(2, 4), ipady=5)
    return e


def _browse_row(parent, var: tk.StringVar, row: int, title: str):
    """Entry + Browse button on same row."""
    frame = tk.Frame(parent, bg=BG2)
    frame.grid(row=row, column=0, columnspan=2,
               sticky="ew", padx=16, pady=(2, 4))
    frame.columnconfigure(0, weight=1)
    e = tk.Entry(frame, textvariable=var,
                 bg=BG3, fg=FG, insertbackground=FG,
                 relief="flat", bd=0, font=("Segoe UI", 9),
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT)
    e.grid(row=0, column=0, sticky="ew", ipady=5, padx=(0, 6))
    btn = tk.Button(frame, text="Browse",
                    command=lambda: _pick_dir(var, title),
                    bg=BG3, fg=FG2, relief="flat", bd=0,
                    font=("Segoe UI", 9), cursor="hand2",
                    activebackground=BORDER, activeforeground=FG,
                    padx=10, pady=4)
    btn.grid(row=0, column=1)
    return e


def _separator(parent, row: int):
    sep = tk.Frame(parent, bg=BORDER, height=1)
    sep.grid(row=row, column=0, columnspan=2,
             sticky="ew", padx=16, pady=8)


def _section_title(parent, text: str, row: int):
    lbl = tk.Label(parent, text=text.upper(), bg=BG2,
                   fg=ACCENT, font=("Segoe UI", 7, "bold"),
                   anchor="w")
    lbl.grid(row=row, column=0, columnspan=2,
             sticky="w", padx=16, pady=(14, 2))


def _check(parent, text: str, var: tk.BooleanVar, row: int):
    cb = tk.Checkbutton(parent, text=text, variable=var,
                        bg=BG2, fg=FG2, selectcolor=BG3,
                        activebackground=BG2, activeforeground=FG,
                        font=("Segoe UI", 9),
                        highlightthickness=0, bd=0, cursor="hand2")
    cb.grid(row=row, column=0, columnspan=2,
            sticky="w", padx=16, pady=2)
    return cb


# ── Main window ──────────────────────────────────────────────────────────────

class PhotoOrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Photo Organizer")
        self.geometry("1020x680")
        self.minsize(820, 560)
        self.configure(bg=BG)
        self._configure_style()

        # ── State vars ───────────────────────────────────────────────────
        self.v_input      = tk.StringVar()
        self.v_output     = tk.StringVar()
        self.v_vault      = tk.StringVar()
        self.v_notes      = tk.StringVar()
        self.v_dry_run    = tk.BooleanVar(value=True)
        self.v_skip_ai    = tk.BooleanVar(value=False)
        self.v_skip_faces = tk.BooleanVar(value=False)
        self.v_skip_video = tk.BooleanVar(value=False)
        self.v_skip_phash = tk.BooleanVar(value=False)
        self.v_dup_report = tk.BooleanVar(value=True)
        self.v_dup_action = tk.StringVar(value="skip")
        self.v_threshold  = tk.IntVar(value=8)
        self.v_no_integrity = tk.BooleanVar(value=False)

        self._process = None
        self._log_queue = queue.Queue()
        self._running = False

        self._build_layout()
        self._load_prefs()
        self.after(100, self._poll_log)

    # ── Style ────────────────────────────────────────────────────────────
    def _configure_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=BG3, background=BG3,
                        foreground=FG, bordercolor=BORDER,
                        arrowcolor=FG2, selectbackground=ACCENT,
                        selectforeground=FG)
        style.map("TCombobox",
                  fieldbackground=[("readonly", BG3)],
                  selectbackground=[("readonly", BG3)],
                  selectforeground=[("readonly", FG)])
        style.configure("TScale",
                        background=BG2, troughcolor=BG3,
                        sliderrelief="flat")

    # ── Layout ───────────────────────────────────────────────────────────
    def _build_layout(self):
        self.columnconfigure(0, weight=0, minsize=340)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_log_panel()

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=BG2, bd=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.columnconfigure(1, weight=0)

        # App header
        header = tk.Frame(sidebar, bg=BG2)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(18, 4))
        tk.Label(header, text="Photo Organizer", bg=BG2, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=16)
        tk.Label(header, text="+ Obsidian", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 10)).pack(side="left")

        # Scrollable content
        canvas = tk.Canvas(sidebar, bg=BG2, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(sidebar, orient="vertical",
                                 command=canvas.yview, bg=BG2,
                                 troughcolor=BG2, bd=0, width=6)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        sidebar.rowconfigure(1, weight=1)

        inner = tk.Frame(canvas, bg=BG2)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.columnconfigure(0, weight=1)

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))

        self._populate_sidebar(inner)

        # Run button
        self._run_btn = tk.Button(
            sidebar, text="Run",
            command=self._on_run,
            bg=ACCENT, fg="#ffffff", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            activebackground="#6657d4", activeforeground="#ffffff",
            padx=0, pady=12,
        )
        self._run_btn.grid(row=2, column=0, columnspan=2,
                           sticky="ew", padx=16, pady=12)

    def _populate_sidebar(self, p):
        row = 0

        # ── Folders ──────────────────────────────────────────────────────
        _section_title(p, "Folders", row); row += 1

        _labeled_row(p, "Source media folder (photos + videos)", row); row += 1
        _browse_row(p, self.v_input,  row, "Select source folder"); row += 1

        _labeled_row(p, "Output folder (inside vault)", row); row += 1
        _browse_row(p, self.v_output, row, "Select output folder"); row += 1

        _labeled_row(p, "Obsidian vault root", row); row += 1
        _browse_row(p, self.v_vault,  row, "Select vault folder"); row += 1

        _labeled_row(p, "Notes folder (optional)", row); row += 1
        _browse_row(p, self.v_notes,  row, "Select notes folder"); row += 1

        _separator(p, row); row += 1

        # ── Options ──────────────────────────────────────────────────────
        _section_title(p, "Options", row); row += 1

        _check(p, "Dry run (preview only — nothing moved)", self.v_dry_run, row); row += 1
        _check(p, "Skip AI scene tagging (faster)",        self.v_skip_ai,    row); row += 1
        _check(p, "Skip face detection",                   self.v_skip_faces,  row); row += 1
        _check(p, "Skip video files (photos only)",        self.v_skip_video,  row); row += 1

        _separator(p, row); row += 1

        # ── Duplicates ───────────────────────────────────────────────────
        _section_title(p, "Duplicate detection", row); row += 1

        _labeled_row(p, "Action on duplicate", row); row += 1
        dup_frame = tk.Frame(p, bg=BG2)
        dup_frame.grid(row=row, column=0, columnspan=2,
                       sticky="ew", padx=16, pady=(2, 6))
        row += 1
        for val, label in [("skip", "Log only"), ("move", "Move to /duplicates"), ("trash", "Delete")]:
            bg_on  = ACCENT if val != "trash" else DANGER
            rb = tk.Radiobutton(
                dup_frame, text=label, variable=self.v_dup_action, value=val,
                bg=BG2, fg=FG2, selectcolor=BG3,
                activebackground=BG2, activeforeground=FG,
                font=("Segoe UI", 9), highlightthickness=0, bd=0,
                cursor="hand2",
                indicatoron=0,
                relief="flat", padx=8, pady=5,
            )
            rb.pack(side="left", padx=(0, 4))
            # color active state dynamically
            rb.configure(
                selectcolor=bg_on,
                fg=FG,
            )

        _check(p, "Generate duplicates_report.md", self.v_dup_report, row); row += 1
        _check(p, "Exact hash only (skip perceptual — faster)", self.v_skip_phash, row); row += 1

        # Threshold slider
        _labeled_row(p, "Perceptual similarity threshold", row); row += 1
        thresh_frame = tk.Frame(p, bg=BG2)
        thresh_frame.grid(row=row, column=0, columnspan=2,
                          sticky="ew", padx=16, pady=(2, 4))
        row += 1
        thresh_frame.columnconfigure(0, weight=1)
        slider = tk.Scale(
            thresh_frame, from_=0, to=20,
            variable=self.v_threshold, orient="horizontal",
            bg=BG2, fg=FG2, troughcolor=BG3,
            highlightthickness=0, bd=0, sliderrelief="flat",
            activebackground=ACCENT, font=("Segoe UI", 8),
            length=200, showvalue=True,
        )
        slider.grid(row=0, column=0, sticky="ew")
        tk.Label(thresh_frame, text="(0 = exact  ·  8 = default  ·  20 = loose)",
                 bg=BG2, fg=FG3, font=("Segoe UI", 8)
                 ).grid(row=1, column=0, sticky="w")

        _separator(p, row); row += 1

        # ── Integrity ─────────────────────────────────────────────────────
        _section_title(p, "Integrity check", row); row += 1

        tk.Label(
            p,
            text=(
                "After each move, the SHA-256 of the destination\n"
                "is compared to the source hash. Any mismatch\n"
                "or missing file is flagged immediately."
            ),
            bg=BG2, fg=FG3, font=("Segoe UI", 8), justify="left",
        ).grid(row=row, column=0, columnspan=2,
               sticky="w", padx=16, pady=(2, 6))
        row += 1

        _check(p, "Disable integrity report (not recommended)",
               self.v_no_integrity, row); row += 1

        # Integrity status indicator (updated after each run)
        self._integrity_frame = tk.Frame(p, bg=BG2)
        self._integrity_frame.grid(row=row, column=0, columnspan=2,
                                   sticky="ew", padx=16, pady=(4, 8))
        row += 1
        self._integrity_dot = tk.Label(
            self._integrity_frame, text="●", bg=BG2, fg=FG3,
            font=("Segoe UI", 11))
        self._integrity_dot.pack(side="left", padx=(0, 6))
        self._integrity_status = tk.Label(
            self._integrity_frame, text="Not yet verified",
            bg=BG2, fg=FG3, font=("Segoe UI", 9))
        self._integrity_status.pack(side="left")

        # ── Faces ─────────────────────────────────────────────────────────
        _section_title(p, "Face labels", row); row += 1

        tk.Button(
            p, text="Edit face labels",
            command=self._open_face_editor,
            bg=ACCENT, fg="#fff", relief="flat", bd=0,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
            activebackground="#6657d4", activeforeground="#fff",
            padx=10, pady=6,
        ).grid(row=row, column=0, columnspan=2,
               sticky="ew", padx=16, pady=(2, 2)); row += 1

        tk.Label(
            p, text="Opens an editor to rename person_00 → Alice, etc.",
            bg=BG2, fg=FG3, font=("Segoe UI", 8), justify="left",
        ).grid(row=row, column=0, columnspan=2,
               sticky="w", padx=16, pady=(0, 8)); row += 1

        _separator(p, row); row += 1

        # ── Maintenance ───────────────────────────────────────────────────
        _section_title(p, "Maintenance", row); row += 1

        tk.Button(
            p, text="Review duplicates side-by-side",
            command=self._on_open_reviewer,
            bg=ACCENT, fg="#fff", relief="flat", bd=0,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
            activebackground="#6657d4", activeforeground="#fff",
            padx=10, pady=6,
        ).grid(row=row, column=0, columnspan=2,
               sticky="ew", padx=16, pady=(2, 2)); row += 1

        tk.Label(
            p,
            text="Compare each duplicate pair visually\nand decide which copy to keep.",
            bg=BG2, fg=FG3, font=("Segoe UI", 8), justify="left",
        ).grid(row=row, column=0, columnspan=2,
               sticky="w", padx=16, pady=(0, 8)); row += 1

        tk.Button(
            p, text="Clean up orphan notes",
            command=self._on_cleanup_notes,
            bg=BG3, fg=FG2, relief="flat", bd=0,
            font=("Segoe UI", 9), cursor="hand2",
            activebackground=BORDER, activeforeground=FG,
            padx=10, pady=6,
        ).grid(row=row, column=0, columnspan=2,
               sticky="w", padx=16, pady=(2, 2)); row += 1

        tk.Label(
            p,
            text="Deletes .md notes whose photo/video\nno longer exists in the vault.",
            bg=BG2, fg=FG3, font=("Segoe UI", 8), justify="left",
        ).grid(row=row, column=0, columnspan=2,
               sticky="w", padx=16, pady=(0, 12)); row += 1

    # ── Log panel ────────────────────────────────────────────────────────
    def _build_log_panel(self):
        panel = tk.Frame(self, bg=BG, bd=0)
        panel.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        # Header bar
        bar = tk.Frame(panel, bg=BG2, height=46)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)

        self._status_dot = tk.Label(bar, text="●", bg=BG2, fg=FG3,
                                    font=("Segoe UI", 11))
        self._status_dot.grid(row=0, column=0, padx=(16, 6), pady=12)

        self._status_lbl = tk.Label(bar, text="Ready", bg=BG2, fg=FG2,
                                    font=("Segoe UI", 9))
        self._status_lbl.grid(row=0, column=1, sticky="w", pady=12)

        clear_btn = tk.Button(bar, text="Clear", command=self._clear_log,
                              bg=BG2, fg=FG3, relief="flat", bd=0,
                              font=("Segoe UI", 8), cursor="hand2",
                              activebackground=BG3, activeforeground=FG2,
                              padx=10, pady=6)
        clear_btn.grid(row=0, column=2, padx=8, pady=6)

        # Log area
        self._log = scrolledtext.ScrolledText(
            panel, bg=BG, fg=FG, insertbackground=FG,
            font=(MONO, 9), relief="flat", bd=0,
            wrap="word", state="disabled",
            selectbackground=ACCENT,
        )
        self._log.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # Tag styles
        self._log.tag_config("info",    foreground=FG)
        self._log.tag_config("ok",      foreground=ACCENT2)
        self._log.tag_config("warn",    foreground="#f0c060")
        self._log.tag_config("err",     foreground=DANGER)
        self._log.tag_config("dup",     foreground="#b07cf0")
        self._log.tag_config("section", foreground=ACCENT,
                              font=(MONO, 9, "bold"))
        self._log.tag_config("video",   foreground="#5bb8d4")
        self._log.tag_config("dim",     foreground=FG3)

        # Stats footer
        self._stats_bar = tk.Frame(panel, bg=BG2, height=32)
        self._stats_bar.grid(row=2, column=0, sticky="ew")
        self._stats_lbl = tk.Label(self._stats_bar, text="",
                                   bg=BG2, fg=FG3,
                                   font=("Segoe UI", 8))
        self._stats_lbl.pack(side="left", padx=16)

    # ── Logging ──────────────────────────────────────────────────────────
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

    def _poll_log(self):
        """Drain the queue and paint new lines — runs on the main thread."""
        counts = {"ok": 0, "dup": 0, "err": 0}
        try:
            while True:
                line, tag = self._log_queue.get_nowait()
                self._log_write(line, tag)
                if tag in counts:
                    counts[tag] += 1
        except queue.Empty:
            pass
        self.after(80, self._poll_log)

    # ── Build CLI args ───────────────────────────────────────────────────
    def _build_args(self) -> list[str]:
        args = [sys.executable, "photo_organizer.py"]

        inp = self.v_input.get().strip()
        out = self.v_output.get().strip()
        vlt = self.v_vault.get().strip()
        if not inp or not out or not vlt:
            raise ValueError("Input, output, and vault folders are required.")

        args += ["--input", inp, "--output", out, "--vault", vlt]

        notes = self.v_notes.get().strip()
        if notes:
            args += ["--notes", notes]
        if self.v_dry_run.get():
            args.append("--dry-run")
        if self.v_skip_ai.get():
            args.append("--skip-ai")
        if self.v_skip_faces.get():
            args.append("--skip-faces")
        if self.v_skip_video.get():
            args.append("--skip-video")
        if self.v_skip_phash.get():
            args.append("--skip-phash")
        if self.v_dup_report.get():
            args.append("--dup-report")

        if self.v_no_integrity.get():
            args.append("--no-integrity-report")

        args += ["--dup-action", self.v_dup_action.get()]
        args += ["--phash-threshold", str(self.v_threshold.get())]

        return args

    # ── Run ──────────────────────────────────────────────────────────────
    def _set_running(self, running: bool):
        self._running = running
        if running:
            self._run_btn.config(text="Stop", bg=DANGER,
                                 command=self._on_stop)
            self._status_dot.config(fg=ACCENT2)
            self._status_lbl.config(text="Running…")
        else:
            self._run_btn.config(text="Run", bg=ACCENT,
                                 command=self._on_run)
            self._status_dot.config(fg=FG3)
            self._status_lbl.config(text="Ready")

    def _on_stop(self):
        if self._process:
            self._process.terminate()
            self._log_write("— Process terminated by user —", "warn")
        self._set_running(False)

    def _on_run(self):
        if self._running:
            return
        try:
            args = self._build_args()
        except ValueError as e:
            messagebox.showerror("Missing fields", str(e))
            return

        # Warn about trash action
        if self.v_dup_action.get() == "trash" and not self.v_dry_run.get():
            if not messagebox.askyesno(
                "Confirm deletion",
                "Duplicate action is set to 'Delete'. "
                "Files will be permanently removed.\n\nContinue?",
            ):
                return

        self._clear_log()
        self._log_write("$ " + " ".join(args), "dim")
        self._log_write("", "dim")
        self._set_running(True)
        self._save_prefs()

        threading.Thread(target=self._run_process,
                         args=(args,), daemon=True).start()

    def _run_process(self, args: list[str]):
        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=Path(__file__).parent,
            )
            photos = moved = dups = errors = 0

            integrity_ok = 0
            integrity_problems = 0

            for raw_line in self._process.stdout:
                line = raw_line.rstrip()
                tag  = "info"

                lower = line.lower()
                if "[integrity]" in lower:
                    if "✓ ok" in lower:
                        tag = "ok"
                        integrity_ok += 1
                    elif "corrupted" in lower or "missing" in lower:
                        tag = "err"
                        integrity_problems += 1
                    else:
                        tag = "warn"
                elif "[video]" in lower:
                    tag = "dup" if "warning" in lower else "section"
                elif "[dup" in lower:
                    tag = "dup"
                    dups += 1
                elif "moved →" in lower or "note  →" in lower:
                    tag = "ok"
                    if "moved →" in lower:
                        moved += 1
                elif "warning" in lower or "warn" in lower or "[dry-run]" in lower:
                    tag = "warn"
                elif "error" in lower or "traceback" in lower:
                    tag = "err"
                    errors += 1
                elif line.startswith("[") and "/" in line[:12]:
                    tag = "video" if "[video]" in line else "section"
                    photos += 1
                elif line.startswith("  "):
                    tag = "dim"

                self._log_queue.put((line, tag))

            self._process.wait()
            rc = self._process.returncode

            # Update integrity indicator on main thread
            def _update_integrity():
                if integrity_problems:
                    self._integrity_dot.config(fg=DANGER)
                    self._integrity_status.config(
                        text=f"{integrity_problems} problem(s) detected — check integrity_report.md",
                        fg=DANGER)
                elif integrity_ok:
                    self._integrity_dot.config(fg=ACCENT2)
                    self._integrity_status.config(
                        text=f"All {integrity_ok} file(s) verified OK",
                        fg=ACCENT2)
            self.after(0, _update_integrity)

            self._log_queue.put(("", "info"))
            if rc == 0:
                summary = (
                    f"✓  Finished — "
                    f"{photos} photo(s) scanned · "
                    f"{moved} moved · "
                    f"{dups} duplicate(s) · "
                    f"{errors} error(s)"
                )
                self._log_queue.put((summary, "ok"))
                self.after(0, lambda: self._stats_lbl.config(text=summary))
            else:
                self._log_queue.put((f"✗  Process exited with code {rc}", "err"))

        except FileNotFoundError:
            self._log_queue.put(
                ("photo_organizer.py not found. Make sure it is in the same folder.", "err")
            )
        except Exception as e:
            self._log_queue.put((f"Error: {e}", "err"))
        finally:
            self.after(0, lambda: self._set_running(False))

    def _on_open_reviewer(self):
        """Launch the side-by-side duplicate reviewer as a separate window."""
        vlt = self.v_vault.get().strip()
        if not vlt:
            messagebox.showerror("Missing vault", "Set the vault folder first.")
            return
        try:
            import importlib.util, subprocess
            reviewer = Path(__file__).parent / "duplicate_reviewer.py"
            if not reviewer.exists():
                messagebox.showerror(
                    "Not found",
                    "duplicate_reviewer.py not found next to this script.",
                )
                return
            cmd = [sys.executable, str(reviewer), "--vault", vlt]
            if self.v_dry_run.get():
                cmd.append("--dry-run")
            subprocess.Popen(cmd)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_rename_faces(self):
        """Run --rename-faces via CLI (called after editor saves)."""
        vlt = self.v_vault.get().strip()
        if not vlt:
            messagebox.showerror("Missing vault", "Please set the Obsidian vault folder first.")
            return
        notes = self.v_notes.get().strip() or str(Path(vlt) / "photo-notes")
        args = [
            sys.executable, "photo_organizer.py",
            "--vault", vlt,
            "--notes", notes,
            "--rename-faces",
        ]
        self._clear_log()
        self._log_write("Applying face renames…", "section")
        self._set_running(True)
        threading.Thread(target=self._run_process, args=(args,), daemon=True).start()

    def _open_face_editor(self):
        """Open an inline editor dialog to rename face labels."""
        vlt = self.v_vault.get().strip()
        if not vlt:
            messagebox.showerror("Missing vault", "Set the vault folder first.")
            return

        labels_file = Path(vlt) / "face_labels.json"
        if not labels_file.exists():
            messagebox.showinfo(
                "No labels yet",
                "Run the organizer first so face_labels.json is created.",
            )
            return

        try:
            labels: dict[str, str] = json.loads(
                labels_file.read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Error", f"Could not read face_labels.json:\n{e}")
            return

        # ── Dialog window ──────────────────────────────────────────────
        dlg = tk.Toplevel(self)
        dlg.title("Edit face labels")
        dlg.geometry("480x420")
        dlg.configure(bg=BG2)
        dlg.resizable(True, True)
        dlg.grab_set()

        tk.Label(dlg, text="Rename auto-detected people",
                 bg=BG2, fg=FG, font=("Segoe UI", 11, "bold")
                 ).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(dlg,
                 text="Left column = auto label  ·  Right column = your name",
                 bg=BG2, fg=FG3, font=("Segoe UI", 8)
                 ).pack(anchor="w", padx=16, pady=(0, 8))

        # Scrollable grid of label pairs
        frame = tk.Frame(dlg, bg=BG2)
        frame.pack(fill="both", expand=True, padx=16)
        frame.columnconfigure(1, weight=1)

        entries: list[tuple[str, tk.StringVar]] = []
        for i, (auto, human) in enumerate(sorted(labels.items())):
            tk.Label(frame, text=auto, bg=BG2, fg=FG2,
                     font=(MONO, 9), anchor="w"
                     ).grid(row=i, column=0, sticky="w",
                            padx=(0, 12), pady=3)
            var = tk.StringVar(value=human)
            e = tk.Entry(frame, textvariable=var,
                         bg=BG3, fg=FG, insertbackground=FG,
                         relief="flat", bd=0, font=("Segoe UI", 9),
                         highlightthickness=1,
                         highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.grid(row=i, column=1, sticky="ew", ipady=4)
            entries.append((auto, var))

        # Buttons
        btn_row = tk.Frame(dlg, bg=BG2)
        btn_row.pack(fill="x", padx=16, pady=12)

        def _save_and_apply():
            updated = {auto: var.get().strip() or auto
                       for auto, var in entries}
            labels_file.write_text(
                json.dumps(updated, indent=2, ensure_ascii=False),
                encoding="utf-8")
            dlg.destroy()
            self._on_rename_faces()

        def _save_only():
            updated = {auto: var.get().strip() or auto
                       for auto, var in entries}
            labels_file.write_text(
                json.dumps(updated, indent=2, ensure_ascii=False),
                encoding="utf-8")
            messagebox.showinfo("Saved",
                "face_labels.json saved.\n"
                "Click 'Apply to notes' to update existing notes.")
            dlg.destroy()

        tk.Button(btn_row, text="Save + apply to notes",
                  command=_save_and_apply,
                  bg=ACCENT, fg="#fff", relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  activebackground="#6657d4",
                  padx=12, pady=6
                  ).pack(side="left", padx=(0, 8))

        tk.Button(btn_row, text="Save only",
                  command=_save_only,
                  bg=BG3, fg=FG2, relief="flat", bd=0,
                  font=("Segoe UI", 9), cursor="hand2",
                  activebackground=BORDER,
                  padx=12, pady=6
                  ).pack(side="left")

        tk.Button(btn_row, text="Cancel",
                  command=dlg.destroy,
                  bg=BG3, fg=FG3, relief="flat", bd=0,
                  font=("Segoe UI", 9), cursor="hand2",
                  padx=12, pady=6
                  ).pack(side="right")

    def _on_cleanup_notes(self):
        """Run --cleanup-notes (with current dry-run setting)."""
        vlt = self.v_vault.get().strip()
        if not vlt:
            messagebox.showerror("Missing vault", "Set the vault folder first.")
            return

        dry = self.v_dry_run.get()
        if not dry:
            if not messagebox.askyesno(
                "Confirm cleanup",
                "This will permanently delete orphan note files "
                "(notes whose photo/video no longer exists).\n\n"
                "Continue?  (Use Dry Run to preview first.)",
            ):
                return

        notes = self.v_notes.get().strip() or str(Path(vlt) / "photo-notes")
        args = [
            sys.executable, "photo_organizer.py",
            "--vault", vlt,
            "--notes", notes,
            "--cleanup-notes",
        ]
        if dry:
            args.append("--dry-run")

        self._clear_log()
        self._log_write(
            f"{'[dry-run] ' if dry else ''}Scanning for orphan notes…",
            "section")
        self._set_running(True)
        threading.Thread(target=self._run_process, args=(args,), daemon=True).start()

    # ── Preferences ──────────────────────────────────────────────────────
    def _prefs_path(self) -> Path:
        return Path(__file__).with_suffix(".prefs.json")

    def _save_prefs(self):
        data = {
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
        }
        try:
            self._prefs_path().write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _load_prefs(self):
        try:
            if not self._prefs_path().exists():
                return
            data = json.loads(self._prefs_path().read_text())
            self.v_input.set(data.get("input", ""))
            self.v_output.set(data.get("output", ""))
            self.v_vault.set(data.get("vault", ""))
            self.v_notes.set(data.get("notes", ""))
            self.v_dry_run.set(data.get("dry_run", True))
            self.v_skip_ai.set(data.get("skip_ai", False))
            self.v_skip_faces.set(data.get("skip_faces", False))
            self.v_skip_video.set(data.get("skip_video", False))
            self.v_skip_phash.set(data.get("skip_phash", False))
            self.v_dup_report.set(data.get("dup_report", True))
            self.v_dup_action.set(data.get("dup_action", "skip"))
            self.v_threshold.set(data.get("threshold", 8))
            self.v_no_integrity.set(data.get("no_integrity", False))
        except Exception:
            pass

    def on_close(self):
        self._save_prefs()
        if self._process:
            self._process.terminate()
        self.destroy()


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = PhotoOrganizerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
