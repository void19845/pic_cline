from __future__ import annotations
"""
organizer.worker
================
Self-contained unit of work for one media file.

Thread-safety contract
----------------------
- _io_lock  : guards _safe_dest -- media FILE placement only (unchanged)
- _log_lock : guards log_fn (may be plain print, not guaranteed thread-safe)
- clip_lock / face_lock : passed in from pipeline
- Duplicate stores are never touched here.
- Vault NOTE writes never happen here -- process_one() builds an entity
  and hands it to VaultWriter.submit(); the writer thread owns every
  vault.upsert() call. See organizer/writer.py for why.

log_fn contract
---------------
process_one() takes a log_fn: Callable[[str], None] instead of calling
print() directly (default: print, so nothing breaks if omitted). This is
what lets the PyQt6 UI capture the exact same lines the CLI prints, via
organizer.reporting.ProgressReporter.log, without parsing stdout.
"""

import shutil
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from organizer.hashing import sha256_of
from organizer.integrity import IntegrityRecord, IntegrityStatus, verify_move
from organizer.media_paths import destination_path, is_video
from organizer.metadata import format_duration, read_exif, read_video_meta, reverse_geocode
from organizer.models import build_photo_note, build_video_note
from organizer.writer import VaultWriter

_io_lock  = threading.Lock()
_log_lock = threading.Lock()


def _safe_dest(dest: Path) -> Path:
    """
    Atomically reserve a non-colliding destination path for a media file.
    Creates an empty placeholder file so other threads see the slot as taken.
    Unchanged from before -- this is about the physical file, which
    obsidian_core has no opinion on.
    """
    with _io_lock:
        final   = dest
        counter = 1
        while final.exists():
            final = dest.parent / f"{dest.stem}_{counter}{dest.suffix}"
            counter += 1
        final.parent.mkdir(parents=True, exist_ok=True)
        final.touch()   # reserve the slot
        return final


@dataclass
class WorkerResult:
    item:        Path
    success:     bool           = False
    error:       str            = ""
    meta:        dict           = field(default_factory=dict)
    city:        str | None     = None
    country:     str | None     = None
    tags:        list[str]      = field(default_factory=list)
    people:      list[str]      = field(default_factory=list)
    final_dest:  Path | None    = None
    note_id:     str | None     = None   # obsidian_core entity id (was note_path)
    irec:        IntegrityRecord | None = None
    face_labels: dict[int, str] = field(default_factory=dict)


def process_one(
    item:         Path,
    output_dir:   Path,
    vault_root:   Path,
    dry_run:      bool,
    skip_ai:      bool,
    skip_faces:   bool,
    clip_lock,
    face_lock,
    vault_writer: VaultWriter | None,
    log_fn:       Callable[[str], None] = print,
) -> WorkerResult:
    def _log(msg: str) -> None:
        with _log_lock:
            log_fn(msg)

    result = WorkerResult(item=item)
    video  = is_video(item)

    try:
        # 1. Metadata
        if video:
            meta = read_video_meta(item)
            _log(f"  [{item.name}] date={meta['date']}  "
                 f"gps=({meta['lat']}, {meta['lon']})  "
                 f"dur={format_duration(meta.get('duration_s'))}  "
                 f"{meta.get('width')}x{meta.get('height')}")
        else:
            meta = read_exif(item)
            _log(f"  [{item.name}] date={meta['date']}  "
                 f"gps=({meta['lat']}, {meta['lon']})")
        result.meta = meta

        # 2. Geocoding
        if meta.get("lat") and meta.get("lon"):
            city, country = reverse_geocode(meta["lat"], meta["lon"])
            result.city    = city
            result.country = country
            _log(f"  [{item.name}] location={city}, {country}")

        # 3. AI tags
        if not video and not skip_ai:
            with clip_lock:
                from organizer.ai_tags import ai_tag
                result.tags = ai_tag(item, log_fn=log_fn)
            _log(f"  [{item.name}] tags={result.tags}")

        # 4. Face detection
        if not video and not skip_faces:
            with face_lock:
                from organizer.faces import detect_faces, get_face_db
                result.people      = detect_faces(item)
                result.face_labels = get_face_db()
            _log(f"  [{item.name}] people={result.people}")

        # 5. Destination path (media file -- independent of the vault/note layer)
        dest = destination_path(output_dir, meta, result.city, item.name)

        # item_rel: path relative to vault for the Obsidian embed / PhotoNote.file_path.
        # If output_dir is outside vault_root, fall back to filename only.
        try:
            item_rel = dest.relative_to(vault_root)
        except ValueError:
            _log(f"  [{item.name}] WARNING: output_dir is outside vault_root -- "
                 f"note embed will use filename only.")
            item_rel = Path(dest.name)

        # 6. Hash source. Reused three ways: dedup (already ran, upstream),
        # integrity verification (below), and the note's stable id (below) --
        # one streamed SHA-256, no redundant re-hashing.
        src_hash = sha256_of(item)
        src_size = item.stat().st_size

        # 7-9. Move / verify / build entity / hand off to the writer
        if not dry_run:
            final_dest = _safe_dest(dest)
            # _safe_dest created a placeholder; shutil.move will overwrite it
            shutil.move(str(item), str(final_dest))
            _log(f"  [{item.name}] moved -> {final_dest}")
            result.final_dest = final_dest

            irec = verify_move(item, final_dest, src_hash)
            result.irec = irec
            if irec.status == IntegrityStatus.OK:
                _log(f"  [{item.name}] [integrity] [OK]  ({src_hash[:12]}...)")
            elif irec.status == IntegrityStatus.MISSING:
                _log(f"  [{item.name}] [integrity] [!!] MISSING")
            elif irec.status == IntegrityStatus.CORRUPTED:
                _log(f"  [{item.name}] [integrity] [!!] CORRUPTED")
                _log(f"    src: {src_hash}")
                _log(f"    dst: {irec.dest_hash}")

            if video:
                entity = build_video_note(
                    item=item, item_rel=item_rel, meta=meta,
                    city=result.city, country=result.country,
                    src_hash=src_hash, src_size=src_size,
                    duration_fmt=format_duration(meta.get("duration_s")),
                )
            else:
                entity = build_photo_note(
                    item=item, item_rel=item_rel, meta=meta,
                    tags=result.tags, people=result.people,
                    city=result.city, country=result.country,
                    src_hash=src_hash, src_size=src_size,
                )

            vault_writer.submit(entity)   # async -- the writer thread persists it
            result.note_id = entity.id
            _log(f"  [{item.name}] note  -> {entity.ENTITY_TYPE}/{entity.id}")

        else:
            # Dry run -- simulate without touching the filesystem or the vault
            sim = dest
            c   = 1
            while sim.exists():
                sim = dest.parent / f"{dest.stem}_{c}{dest.suffix}"
                c  += 1
            _log(f"  [{item.name}] [dry-run] would move -> {sim}")
            result.final_dest = sim
            result.irec = IntegrityRecord(
                source=str(item), destination=str(sim),
                source_hash=src_hash, dest_hash=None,
                status=IntegrityStatus.SKIPPED, size_src=src_size,
            )

        result.success = True

    except Exception as exc:
        tb_last = traceback.format_exc().splitlines()
        result.error   = str(exc)
        result.success = False
        _log(f"  [{item.name}] ERROR: {exc}")
        # Print the last two traceback lines for quick diagnosis
        for line in tb_last[-3:]:
            _log(f"  [{item.name}]   {line}")

    return result
