#!/usr/bin/env python3
"""
photo_organizer.py — CLI entry point
=====================================
All logic lives in the ``organizer/`` package.  This file is intentionally
thin: it parses arguments and delegates to the appropriate module.

Usage
-----
    # Sort photos + videos
    python photo_organizer.py --input ~/Downloads/media \
                              --output ~/vault/media    \
                              --vault  ~/vault

    # Maintenance only (no --input / --output needed)
    python photo_organizer.py --vault ~/vault --rename-faces
    python photo_organizer.py --vault ~/vault --cleanup-notes [--dry-run]
"""

from __future__ import annotations
import argparse
import sys
import warnings
from pathlib import Path

# ── Force UTF-8 output on Windows (cp1252 can't encode -> [OK] etc.) ─────────────
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Suppress noisy but harmless third-party warnings at startup
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Silence HuggingFace symlink warning via env (must be set before any HF import)
import os
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="photo_organizer",
        description="Sort photos/videos and generate Obsidian notes.",
    )
    p.add_argument("--input",  default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--vault",  required=True)
    p.add_argument("--notes",  default=None,
                   help="Deprecated: ignored. Notes always go to "
                        "<vault>/photo-notes (obsidian_core.PhotoNote."
                        "VAULT_SUBPATH). Kept only so old scripts/prefs "
                        "don't break when they still pass it.")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Skip the interactive trash confirmation "
                        "(required when stdin isn't a TTY, e.g. launched "
                        "from the UI as a subprocess).")
    p.add_argument("--dry-run",    action="store_true")
    p.add_argument("--skip-ai",    action="store_true")
    p.add_argument("--skip-faces", action="store_true")
    p.add_argument("--skip-video", action="store_true")
    p.add_argument("--dup-action", choices=["skip","move","trash"], default="skip")
    p.add_argument("--dup-report", action="store_true")
    p.add_argument("--skip-phash", action="store_true")
    p.add_argument("--phash-threshold", type=int, default=8)
    p.add_argument("--io-workers", type=int, default=None, metavar="N",
                   help="I/O thread count  [default: cpu_count-1]")
    p.add_argument("--ai-workers", type=int, default=None, metavar="N",
                   help="Max concurrent AI inferences  [default: cpu_count//2]")
    p.add_argument("--no-integrity-report", action="store_true")
    p.add_argument("--rename-faces",  action="store_true")
    p.add_argument("--cleanup-notes", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    vault_root = Path(args.vault).expanduser().resolve()

    # Notes always live at <vault>/photo-notes now (PhotoNote/VideoNote.
    # VAULT_SUBPATH in obsidian_core is fixed, not app-configurable — that's
    # the point of the shared schema). --notes is accepted but ignored.
    notes_dir = vault_root / "photo-notes"
    if args.notes and Path(args.notes).expanduser().resolve() != notes_dir:
        print(f"[WARNING] --notes is deprecated and ignored — notes always "
              f"go to {notes_dir}")

    if args.rename_faces:
        from organizer.maintenance import apply_face_renames
        apply_face_renames(vault_root, notes_dir)
        return

    if args.cleanup_notes:
        from organizer.maintenance import cleanup_orphan_notes
        cleanup_orphan_notes(notes_dir, vault_root, dry_run=args.dry_run)
        return

    if not args.input or not args.output:
        print("error: --input and --output are required.", file=sys.stderr)
        sys.exit(1)

    input_dir  = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    if not input_dir.exists():
        print(f"error: input folder not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    if args.dup_action == "trash" and not args.dry_run and not args.yes:
        if not sys.stdin.isatty():
            # No interactive terminal attached (e.g. launched by the UI as a
            # subprocess) -- input() would raise EOFError here. Refuse
            # instead of hanging/crashing; caller must pass --yes.
            print("error: --dup-action trash requires --yes when not running "
                  "in an interactive terminal.", file=sys.stderr)
            sys.exit(1)
        if input("\nWARNING: will permanently delete duplicates. Type 'yes': "
                 ).strip().lower() != "yes":
            print("Aborted."); return

    import organizer.duplicates as _dup
    _dup.PHASH_THRESHOLD = args.phash_threshold

    from organizer.pipeline import process_vault
    process_vault(
        input_dir=input_dir, output_dir=output_dir,
        vault_root=vault_root,
        dry_run=args.dry_run, skip_ai=args.skip_ai,
        skip_faces=args.skip_faces, skip_video=args.skip_video,
        dup_action=args.dup_action,
        skip_phash=args.skip_phash,
        integrity_report=not args.no_integrity_report,
        io_workers=args.io_workers,
        ai_workers=args.ai_workers,
    )


if __name__ == "__main__":
    main()
