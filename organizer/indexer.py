from __future__ import annotations
"""
organizer.indexer
=================
Pre-index all media files already present in the vault before a sort run.

Why this is needed
------------------
``check_duplicate`` only compares incoming files against each other within
the current run.  Without pre-indexing, a photo already sorted into the
vault on a previous run would never be detected as a duplicate of a new
incoming file.

What it does
------------
1. Recursively scan every file under ``vault_root`` whose extension is a
   supported media type (photos + optionally videos).
2. For each file call ``seed_from_existing(path, skip_phash)`` which
   registers it in the in-memory SHA-256 and pHash stores without
   treating it as a duplicate.
3. After this call, the main pipeline's ``check_duplicate()`` will
   correctly detect incoming files that already exist anywhere in the vault.

Skipped paths
-------------
- ``vault_root/duplicates/``     — already-quarantined duplicates
- ``vault_root/photo-notes/``    — Markdown notes, not media
- Files whose name starts with '.'

Performance notes
-----------------
- SHA-256 is I/O-bound and fast (~200 MB/s on an average SSD).
  A 10 GB vault (~3 000 photos) indexes in about 50 seconds.
- pHash adds ~0.5-2 s per photo (CPU-bound).  With ``skip_phash=True``
  only SHA-256 is computed and indexing is 10-50x faster.
- The function is intentionally single-threaded to keep the main thread
  responsive and avoid contending with the worker pool that starts right after.
"""

from pathlib import Path
from typing import Callable

from .duplicates import seed_from_existing
from .metadata   import SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS

# Subdirectory names under vault_root that should never be indexed
_SKIP_DIRS = frozenset({
    "duplicates",
    ".duplicates",
    "photo-notes",
    ".obsidian",
    ".git",
    ".trash",
})


def index_vault(
    vault_root:  Path,
    skip_phash:  bool = False,
    skip_video:  bool = False,
    input_dir:   Path | None = None,
    log_fn:      Callable[[str], None] = print,
) -> int:
    """
    Pre-seed the duplicate stores with every media file already in the vault.

    Parameters
    ----------
    vault_root  : root of the Obsidian vault to scan
    skip_phash  : if True, only SHA-256 is computed (faster, no near-dup detection)
    skip_video  : if True, video files are excluded from the index
    input_dir   : source folder for this run — excluded from the index so that
                  incoming files are not pre-registered as "existing" before
                  they are processed (would prevent self-dedup within the batch)
    log_fn      : sink for progress lines (default: print). The UI passes
                  organizer.reporting.ProgressReporter.log here instead.

    Returns
    -------
    Number of files indexed.
    """
    active_exts = SUPPORTED_EXTENSIONS | (set() if skip_video else VIDEO_EXTENSIONS)

    # Normalise input_dir for exclusion comparison
    input_dir_resolved = input_dir.resolve() if input_dir else None

    indexed = 0
    skipped = 0

    log_fn(f"\n[index] Pre-indexing vault: {vault_root}")
    log_fn(f"[index] Mode: {'SHA-256 only' if skip_phash else 'SHA-256 + pHash'}")

    for item in sorted(vault_root.rglob("*")):
        # Skip directories and hidden files
        if item.is_dir():
            continue
        if item.name.startswith("."):
            continue

        # Skip blacklisted top-level subdirectories
        try:
            relative_parts = item.relative_to(vault_root).parts
            if relative_parts and relative_parts[0] in _SKIP_DIRS:
                continue
        except ValueError:
            pass

        # Skip the source input directory itself (those files are the incoming batch)
        if input_dir_resolved:
            try:
                item.resolve().relative_to(input_dir_resolved)
                continue   # this file is inside the input folder — skip it
            except ValueError:
                pass       # not inside input_dir — proceed normally

        # Only index media files
        if item.suffix.lower() not in active_exts:
            continue

        seed_from_existing(item, skip_phash=skip_phash, log_fn=log_fn)
        indexed += 1

        # Progress heartbeat every 100 files
        if indexed % 100 == 0:
            log_fn(f"[index]   {indexed} files indexed so far...")

    log_fn(f"[index] Done — {indexed} file(s) indexed, {skipped} skipped\n")
    return indexed
