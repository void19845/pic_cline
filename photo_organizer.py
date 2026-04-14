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
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="photo_organizer",
        description="Sort photos/videos and generate Obsidian notes.",
    )
    p.add_argument("--input",  default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--vault",  required=True)
    p.add_argument("--notes",  default=None)
    p.add_argument("--dry-run",    action="store_true")
    p.add_argument("--skip-ai",    action="store_true")
    p.add_argument("--skip-faces", action="store_true")
    p.add_argument("--skip-video", action="store_true")
    p.add_argument("--dup-action", choices=["skip","move","trash"], default="skip")
    p.add_argument("--dup-report", action="store_true")
    p.add_argument("--skip-phash", action="store_true")
    p.add_argument("--phash-threshold", type=int, default=8)
    p.add_argument("--no-integrity-report", action="store_true")
    p.add_argument("--rename-faces",  action="store_true")
    p.add_argument("--cleanup-notes", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    vault_root = Path(args.vault).expanduser().resolve()
    notes_dir  = (Path(args.notes).expanduser().resolve()
                  if args.notes else vault_root / "photo-notes")

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

    if args.dup_action == "trash" and not args.dry_run:
        if input("\nWARNING: will permanently delete duplicates. Type 'yes': "
                 ).strip().lower() != "yes":
            print("Aborted."); return

    import organizer.duplicates as _dup
    _dup.PHASH_THRESHOLD = args.phash_threshold

    from organizer.pipeline import process_vault
    process_vault(
        input_dir=input_dir, output_dir=output_dir,
        vault_root=vault_root, notes_dir=notes_dir,
        dry_run=args.dry_run, skip_ai=args.skip_ai,
        skip_faces=args.skip_faces, skip_video=args.skip_video,
        dup_action=args.dup_action, dup_report=args.dup_report,
        skip_phash=args.skip_phash,
        integrity_report=not args.no_integrity_report,
    )


if __name__ == "__main__":
    main()
