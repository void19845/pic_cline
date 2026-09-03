from __future__ import annotations
"""
organizer.pipeline
==================
Main orchestration loop -- hybrid parallel execution.

Concurrency model
-----------------
+- Main thread (sequential) --------------------------------------+
|  scan -> dedup check -> dispatch -> collect -> reports          |
+-------------------------------------------------------------------+
         |  submit futures
         v
+- ThreadPoolExecutor (io_workers) --------------------------------+
|  per-file: EXIF - geocode - CLIP* - faces* - move - integrity    |
|            build entity -> hand off to VaultWriter               |
+-------------------------------------------------------------------+
   * CLIP and face detection are CPU-heavy; each acquires a shared
     Lock before calling the model, so at most one inference runs
     at a time while I/O continues in other threads.

+- VaultWriter (1 dedicated thread) --------------------------------+
|  drains a queue of entities, calls vault.upsert() one at a time  |
+---------------------------------------------------------------------+
   Every note write goes through this single thread -- workers never
   call vault.upsert() themselves. See organizer/writer.py for why.

Reporting
---------
Every print() has been replaced with reporter.log() / reporter.progress()
/ reporter.finished() (organizer.reporting.ProgressReporter). Nothing in
this module or its callees imports Qt. The default reporter
(ConsoleReporter) reproduces the exact prior stdout output, so the CLI
is unaffected. The PyQt6 UI (ui/pipeline_bridge.py) supplies a QtReporter
that emits signals instead of printing -- that's the only file where
Qt and organizer/ meet.

Why ThreadPoolExecutor (not ProcessPool)?
-----------------------------------------
The CLIP model is loaded once and lives in the main process.
Sharing it across processes would require pickling (not supported
for PyTorch modules) or inter-process memory mapping.
Threads share memory directly, so the model reference is passed as-is.
The GIL is released during PyTorch C++ inference and during all I/O
(file reads/writes, socket calls for geocoding), so threads give real
parallelism for our use case.

Worker count
------------
  io_workers  -- threads for I/O + AI   (default: cpu_count - 1, min 1)
  ai_workers  -- max concurrent AI jobs  (default: cpu_count // 2, min 1)
               enforced via a threading.Semaphore so at most N threads
               run CLIP/face detection simultaneously even if io_workers > N.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core import VaultManager

from organizer.ai_tags import preload_clip
from organizer.dup_report import DupPair, build_dup_pair, merge_and_save
from organizer.duplicates import check_duplicate, handle_duplicate, reset_stores
from organizer.indexer import index_vault
from organizer.integrity import IntegrityRecord, IntegrityStatus, write_integrity_report
from organizer.media_paths import is_video
from organizer.metadata import SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS
from organizer.reporting import ConsoleReporter, ProgressReporter, RunSummary
from organizer.writer import VaultWriter
from .worker import WorkerResult, process_one


def _default_io_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


def _default_ai_workers() -> int:
    return max(1, (os.cpu_count() or 2) // 2)


def process_vault(
    input_dir:        Path,
    output_dir:       Path,
    vault_root:       Path,
    dry_run:          bool = False,
    skip_ai:          bool = False,
    skip_faces:       bool = False,
    skip_video:       bool = False,
    dup_action:       str  = "skip",
    skip_phash:       bool = False,
    integrity_report: bool = True,
    io_workers:       int | None = None,
    ai_workers:       int | None = None,
    reporter:         ProgressReporter | None = None,
) -> RunSummary:
    """
    Process all media in *input_dir* using a hybrid thread pool.

    Parameters
    ----------
    io_workers  : threads for I/O-bound work  (default: cpu_count - 1)
    ai_workers  : max concurrent AI inferences (default: cpu_count // 2)
    reporter    : ProgressReporter to receive log/progress/finished calls.
                  Defaults to ConsoleReporter() (prints exactly as before).
                  The PyQt6 UI passes a QtReporter here instead.

    Notes go to <vault_root>/photo-notes/... always -- this is
    PhotoNote.VAULT_SUBPATH / VideoNote.VAULT_SUBPATH in obsidian_core,
    fixed by the shared library so every app's vault layout stays
    predictable. There is no separate notes_dir to configure anymore.

    Returns a RunSummary (also passed to reporter.finished()).
    """
    r = reporter or ConsoleReporter()
    n_io = io_workers if io_workers is not None else _default_io_workers()
    n_ai = ai_workers if ai_workers is not None else _default_ai_workers()

    # -- Validate paths -------------------------------------------------------
    input_dir  = input_dir.resolve()
    output_dir = output_dir.resolve()
    vault_root = vault_root.resolve()

    try:
        output_dir.relative_to(vault_root)
    except ValueError:
        r.log(f"\n[WARNING] output_dir is not inside vault_root!")
        r.log(f"  vault_root : {vault_root}")
        r.log(f"  output_dir : {output_dir}")
        r.log(f"  Obsidian note embed paths will use filenames only.")
        r.log(f"  For full graph-view links, set output_dir inside the vault.\n")

    active_exts = SUPPORTED_EXTENSIONS | (set() if skip_video else VIDEO_EXTENSIONS)
    media = sorted(p for p in input_dir.rglob("*")
                   if p.suffix.lower() in active_exts)

    photos = [p for p in media if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    videos = [p for p in media if p.suffix.lower() in VIDEO_EXTENSIONS]
    r.log(f"\nFound {len(photos)} photo(s) and {len(videos)} video(s) in {input_dir}")
    r.log(f"Workers: {n_io} I/O threads - {n_ai} max concurrent AI inferences\n")

    summary = RunSummary(photos_found=len(photos), videos_found=len(videos), dry_run=dry_run)

    # -- Reset stores then pre-index vault -------------------------------------
    # Always start fresh so a re-run doesn't carry stale hashes from last time.
    reset_stores()

    # Index all media already in the vault so that incoming files are compared
    # against the FULL vault content, not just against each other.
    index_vault(
        vault_root  = vault_root,
        skip_phash  = skip_phash,
        skip_video  = skip_video,
        input_dir   = input_dir,   # excluded -- these are the incoming files
        log_fn      = r.log,
    )

    # -- Preload CLIP once before spawning threads -----------------------------
    if not skip_ai:
        preload_clip(log_fn=r.log)

    # -- Shared resources -------------------------------------------------------
    vault = VaultManager(vault_root)
    vault.bootstrap()
    writer = VaultWriter(vault)
    if not dry_run:
        writer.start()

    dup_dir = vault_root / "duplicates"

    clip_lock = threading.Lock()          # one CLIP inference at a time
    face_lock = threading.Lock()          # one face-rec call at a time
    ai_sem    = threading.Semaphore(n_ai) # cap concurrent AI jobs

    # Wrap locks with semaphore so at most n_ai threads enter AI sections
    class _SemLock:
        """Combines a Semaphore and a Lock: acquire sem then lock."""
        def __init__(self, sem: threading.Semaphore, lock: threading.Lock):
            self._sem  = sem
            self._lock = lock
        def __enter__(self):
            self._sem.acquire()
            self._lock.acquire()
            return self
        def __exit__(self, *_):
            self._lock.release()
            self._sem.release()

    bounded_clip  = _SemLock(ai_sem, clip_lock)
    bounded_face  = _SemLock(ai_sem, face_lock)

    # -- Sequential dedup -> parallel dispatch ---------------------------------
    new_dup_pairs:      list[DupPair]         = []
    integrity_records:  list[IntegrityRecord] = []
    face_labels_merged: dict[int, str]        = {}
    skipped   = 0
    completed = 0   # items FULLY done (sync duplicate-skip or a finished future)
    total     = len(media)
    futures   = {}   # future -> item

    with ThreadPoolExecutor(max_workers=n_io) as pool:
        for idx, item in enumerate(media, 1):
            video = is_video(item)
            r.log(f"[{idx}/{total}] {item.name}  "
                  f"[{'video' if video else 'photo'}]  checking...")

            # -- Dedup check (sequential, main thread) --------------------
            dup = check_duplicate(item, skip_phash=(skip_phash or video), log_fn=r.log)
            if dup.is_duplicate:
                dup_kind = "exact" if dup.is_exact else "perceptual"
                pair = build_dup_pair(
                    original_path  = dup.original,
                    duplicate_path = item,
                    sha_original   = dup.sha_original,
                    sha_duplicate  = dup.sha_current,
                    kind           = dup_kind,
                    phash_distance = dup.phash_distance,
                    vault_root     = vault_root,
                )
                new_dup_pairs.append(pair)

                if not dup.keep_current:
                    handle_duplicate(item, dup, dup_action, dup_dir, dry_run, log_fn=r.log)
                    skipped += 1
                    irec = IntegrityRecord(
                        source=str(item), destination=str(item),
                        source_hash=dup.sha_current or "",
                        dest_hash=None, status=IntegrityStatus.SKIPPED,
                    )
                    integrity_records.append(irec)
                    completed += 1
                    r.progress(completed, total)
                    continue

            # -- Dispatch to thread pool -----------------------------------
            fut = pool.submit(
                process_one,
                item         = item,
                output_dir   = output_dir,
                vault_root   = vault_root,
                dry_run      = dry_run,
                skip_ai      = skip_ai,
                skip_faces   = skip_faces,
                clip_lock    = bounded_clip,
                face_lock    = bounded_face,
                vault_writer = writer,
                log_fn       = r.log,
            )
            futures[fut] = item

        # -- Collect results as they complete --------------------------
        for fut in as_completed(futures):
            item: Path = futures[fut]
            try:
                result: WorkerResult = fut.result()
            except Exception as exc:
                r.log(f"  [ERROR] {item.name}: {exc}")
                completed += 1
                r.progress(completed, total)
                continue

            if result.irec is not None:
                integrity_records.append(result.irec)

            # Merge face labels (last writer wins per cluster_id)
            face_labels_merged.update(result.face_labels)
            completed += 1
            r.progress(completed, total)

    # -- Drain the vault writer and report any failures ------------------------
    if not dry_run:
        writer.stop_and_join()
        r.log(f"\nVault: {writer.written} note(s) written")
        if writer.errors:
            r.log(f"  !! {len(writer.errors)} note(s) FAILED to write:")
            for err in writer.errors:
                r.log(f"     {err.entity_type}/{err.entity_id}: {err.error}")
        summary.notes_written = writer.written
        summary.write_errors  = len(writer.errors)

    # -- Save face labels map ----------------------------------------------------
    if not dry_run and face_labels_merged:
        labels_file = vault_root / "face_labels.json"
        existing: dict[str, str] = {}
        if labels_file.exists():
            try:
                existing = json.loads(labels_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        for label in face_labels_merged.values():
            if label not in existing:
                existing[label] = label
        labels_file.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8")
        r.log(f"\nFace label map -> {labels_file}")
        r.log("Edit via 'Edit face labels' in the UI (or --rename-faces on CLI).")

    # -- Merge duplicates into Markdown report -----------------------------------
    r.log(f"\nDuplicates this run: {len(new_dup_pairs)} found  |  {skipped} actioned")
    merge_and_save(vault_root, new_dup_pairs, dry_run=dry_run, log_fn=r.log)
    summary.duplicates_found    = len(new_dup_pairs)
    summary.duplicates_actioned = skipped
    summary.dup_report_path     = vault_root / "duplicates_report.md"

    # -- Integrity summary ---------------------------------------------------------
    ok_n   = sum(1 for rec in integrity_records if rec.status == IntegrityStatus.OK)
    miss_n = sum(1 for rec in integrity_records if rec.status == IntegrityStatus.MISSING)
    corp_n = sum(1 for rec in integrity_records if rec.status == IntegrityStatus.CORRUPTED)
    r.log(f"Integrity: {ok_n} OK  |  {miss_n} missing  |  {corp_n} corrupted")
    if miss_n or corp_n:
        r.log("  !! PROBLEMS DETECTED -- review integrity_report.md !!")
    summary.integrity_ok        = ok_n
    summary.integrity_missing   = miss_n
    summary.integrity_corrupted = corp_n

    if integrity_report:
        write_integrity_report(vault_root, integrity_records, dry_run, log_fn=r.log)
        summary.integrity_report_path = vault_root / "integrity_report.md"

    r.log("Done.")
    r.finished(summary)
    return summary