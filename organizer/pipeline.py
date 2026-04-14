from __future__ import annotations
"""organizer.pipeline — main media processing loop."""

import json
import shutil
from pathlib import Path

from organizer.ai_tags import ai_tag
from organizer.database import init_db, log_duplicate, log_integrity, log_photo
from organizer.duplicates import (check_duplicate, handle_duplicate)
from organizer.faces import detect_faces, get_face_db
from organizer.hashing import sha256_of
from organizer.integrity import IntegrityRecord, IntegrityStatus, verify_move, write_integrity_report
from organizer.metadata import (SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS,
                                format_duration, read_exif, read_video_meta,
                                reverse_geocode)
from organizer.notes import (build_obsidian_note, build_video_note,
                             destination_path, is_video)


def _safe_note_path(notes_dir: Path, stem: str) -> Path:
    """Return a non-colliding .md path under notes_dir."""
    path = notes_dir / f"{stem}.md"
    counter = 1
    while path.exists():
        path = notes_dir / f"{stem}_{counter}.md"
        counter += 1
    return path


def _safe_dest(dest: Path) -> Path:
    """Return a non-colliding destination path."""
    final = dest
    counter = 1
    while final.exists():
        final = dest.parent / f"{dest.stem}_{counter}{dest.suffix}"
        counter += 1
    return final


def process_vault(
    input_dir: Path,
    output_dir: Path,
    vault_root: Path,
    notes_dir: Path,
    dry_run: bool = False,
    skip_ai: bool = False,
    skip_faces: bool = False,
    skip_video: bool = False,
    dup_action: str = "skip",
    dup_report: bool = False,
    skip_phash: bool = False,
    integrity_report: bool = True,
) -> None:
    """
    Main orchestration loop.

    For each file in *input_dir* (recursively):
      1. Duplicate check (exact SHA-256; + pHash for photos if not skip_phash)
      2. Metadata extraction (EXIF for photos, ffprobe for videos)
      3. Reverse geocoding
      4. AI scene tagging  (photos only, unless skip_ai)
      5. Face detection    (photos only, unless skip_faces)
      6. Move to structured destination path
      7. SHA-256 integrity verification
      8. Write Obsidian .md note
      9. Log to SQLite database
    """
    active_exts = SUPPORTED_EXTENSIONS | (set() if skip_video else VIDEO_EXTENSIONS)
    media = sorted(p for p in input_dir.rglob("*")
                   if p.suffix.lower() in active_exts)

    photos = [p for p in media if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    videos = [p for p in media if p.suffix.lower() in VIDEO_EXTENSIONS]
    print(f"\nFound {len(photos)} photo(s) and {len(videos)} video(s) in {input_dir}\n")

    db_path = vault_root / "photo_organizer.db"
    dup_dir = vault_root / "duplicates"
    conn    = init_db(db_path)

    dup_log:           list[dict]           = []
    integrity_records: list[IntegrityRecord] = []
    skipped = 0

    for idx, item in enumerate(media, 1):
        video = is_video(item)
        print(f"[{idx}/{len(media)}] {item.name}  [{'video' if video else 'photo'}]")

        # ── 1. Duplicate check ───────────────────────────────────────────
        dup = check_duplicate(item, skip_phash=(skip_phash or video))
        if dup.is_duplicate:
            dup_kind = "exact" if dup.is_exact else "perceptual"
            if not dry_run:
                log_duplicate(conn, str(item), str(dup.original),
                              dup_kind, dup_action, dup.keep_current)
            dup_log.append({
                "file": item.name, "original": dup.original.name,
                "kind": dup_kind, "kept": dup.keep_current, "action": dup_action,
            })
            if not dup.keep_current:
                handle_duplicate(item, dup, dup_action, dup_dir, dry_run)
                skipped += 1
                irec = IntegrityRecord(
                    source=str(item), destination=str(item),
                    source_hash=sha256_of(item) if item.exists() else "",
                    dest_hash=None, status=IntegrityStatus.SKIPPED,
                )
                integrity_records.append(irec)
                if not dry_run:
                    log_integrity(conn, irec)
                continue

        # ── 2. Metadata ──────────────────────────────────────────────────
        if video:
            meta = read_video_meta(item)
            print(f"  date={meta['date']}  "
                  f"gps=({meta['lat']}, {meta['lon']})  "
                  f"dur={format_duration(meta.get('duration_s'))}  "
                  f"{meta.get('width')}x{meta.get('height')}")
        else:
            meta = read_exif(item)
            print(f"  date={meta['date']}  gps=({meta['lat']}, {meta['lon']})")

        # ── 3. Reverse geocoding ─────────────────────────────────────────
        city = country = None
        if meta.get("lat") and meta.get("lon"):
            city, country = reverse_geocode(meta["lat"], meta["lon"])
            print(f"  location={city}, {country}")

        # ── 4 & 5. AI tags + faces (photos only) ────────────────────────
        tags:   list[str] = []
        people: list[str] = []
        if not video:
            if not skip_ai:
                tags = ai_tag(item)
                print(f"  tags={tags}")
            if not skip_faces:
                people = detect_faces(item)
                print(f"  people={people}")

        # ── 6. Destination + move ────────────────────────────────────────
        dest      = destination_path(output_dir, meta, city, item.name)
        item_rel  = dest.relative_to(vault_root)
        src_hash  = sha256_of(item)
        src_size  = item.stat().st_size

        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            final_dest = _safe_dest(dest)
            shutil.move(str(item), final_dest)
            print(f"  moved → {final_dest}")

            # ── 7. Integrity ─────────────────────────────────────────────
            irec = verify_move(item, final_dest, src_hash)
            integrity_records.append(irec)
            log_integrity(conn, irec)

            if irec.status == IntegrityStatus.OK:
                print(f"  [integrity] ✓ OK  ({src_hash[:12]}…)")
            elif irec.status == IntegrityStatus.MISSING:
                print(f"  [integrity] ✗ MISSING — destination not found!")
            elif irec.status == IntegrityStatus.CORRUPTED:
                print(f"  [integrity] ✗ CORRUPTED — hash mismatch!")
                print(f"              src: {src_hash}")
                print(f"              dst: {irec.dest_hash}")

            # ── 8. Obsidian note ─────────────────────────────────────────
            rel_str = str(item_rel).replace("\\", "/")
            if video:
                content = build_video_note(rel_str, meta, city, country)
            else:
                content = build_obsidian_note(
                    rel_str, meta, tags, people, city, country)

            notes_dir.mkdir(parents=True, exist_ok=True)
            note_path = _safe_note_path(notes_dir, item.stem)
            note_path.write_text(content, encoding="utf-8")
            print(f"  note  → {note_path}")

            # ── 9. DB log ────────────────────────────────────────────────
            log_photo(conn, str(item), str(final_dest),
                      meta, city, country,
                      tags if not video else ["video"],
                      people)

        else:
            final_dest = _safe_dest(dest)
            print(f"  [dry-run] would move → {final_dest}")
            irec = IntegrityRecord(
                source=str(item), destination=str(final_dest),
                source_hash=src_hash, dest_hash=None,
                status=IntegrityStatus.SKIPPED, size_src=src_size,
            )
            integrity_records.append(irec)

    # ── Save face labels map ─────────────────────────────────────────────────
    face_db = get_face_db()
    if not dry_run and face_db:
        labels_file = vault_root / "face_labels.json"
        existing: dict[str, str] = {}
        if labels_file.exists():
            try:
                existing = json.loads(labels_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Only add new keys; never overwrite existing renames
        for label in face_db.values():
            if label not in existing:
                existing[label] = label
        labels_file.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nFace label map → {labels_file}")
        print("Edit it to rename person_00 → 'Alice', then use 'Edit face "
              "labels' in the UI (or --rename-faces on the CLI).")

    # ── Summaries ────────────────────────────────────────────────────────────
    print(f"\nDuplicates: {len(dup_log)} found  |  {skipped} actioned")
    if dup_report and dup_log:
        _write_dup_report(vault_root, dup_log, dry_run)

    ok_n   = sum(1 for r in integrity_records if r.status == IntegrityStatus.OK)
    miss_n = sum(1 for r in integrity_records if r.status == IntegrityStatus.MISSING)
    corp_n = sum(1 for r in integrity_records if r.status == IntegrityStatus.CORRUPTED)
    print(f"Integrity:  {ok_n} OK  |  {miss_n} missing  |  {corp_n} corrupted")
    if miss_n or corp_n:
        print("  !! PROBLEMS DETECTED — review integrity_report.md !!")

    if integrity_report:
        write_integrity_report(vault_root, integrity_records, dry_run)

    conn.close()
    print("Done.")


def _write_dup_report(vault_root: Path, dup_log: list[dict], dry_run: bool) -> None:
    """Write ``duplicates_report.md`` to vault root."""
    from datetime import datetime
    lines = [
        "# Duplicates report", "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
        "| File | Duplicate of | Type | Action | Kept? |",
        "|------|-------------|------|--------|-------|",
    ]
    for d in dup_log:
        kept = "yes (higher res)" if d["kept"] else "no"
        lines.append(
            f"| {d['file']} | {d['original']} | {d['kind']} | {d['action']} | {kept} |"
        )
    report = vault_root / "duplicates_report.md"
    if not dry_run:
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nDuplicate report → {report}")
    else:
        print(f"\n[dry-run] would write duplicate report → {report}")
