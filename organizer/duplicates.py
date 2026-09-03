from __future__ import annotations
"""organizer.duplicates — exact and perceptual duplicate detection."""

import shutil
from pathlib import Path
from typing import Callable

from .hashing import sha256_of, phash_of, pixel_count

# ── Module-level state (reset between test runs if needed) ──────────────────
PHASH_THRESHOLD: int = 8          # Hamming distance; 0=identical ≤10=near-dup

_exact_hashes: dict[str, tuple[Path, int]] = {}  # sha256 -> (first-seen path, pixel_count)
_phash_store:  list[tuple]                 = []  # [(phash_obj, path), ...]

# NOTE on the (path, pixel_count) tuple: pixel_count is cached at
# registration time rather than re-read from disk on every comparison.
# check_duplicate() runs on the main thread and dispatches to a worker
# pool that moves files asynchronously — by the time a later exact-dup
# match wants to compare quality against an earlier "original", that
# original may already have been shutil.move()'d away by its worker
# thread. pixel_count() returns 0 on any read error (including a
# missing file), which would silently make keep_current=True for the
# wrong reason. Caching the value once, synchronously, before dispatch
# removes the race entirely instead of returning a wrong answer.


def reset_stores() -> None:
    """Clear in-memory duplicate stores (useful for tests)."""
    _exact_hashes.clear()
    _phash_store.clear()


def seed_from_existing(
    path: Path,
    skip_phash: bool = False,
    log_fn: "Callable[[str], None]" = print,
) -> None:
    """
    Register an already-existing vault file in the duplicate stores WITHOUT
    declaring it a duplicate.  Call this during vault pre-indexing so that
    incoming source files are compared against the full vault content, not
    just against each other.

    Unlike check_duplicate():
    - Never returns a DuplicateResult — the file IS the reference
    - Silently skips files already registered (same sha256)
    - Does not apply the "keep higher-quality copy" logic — first-seen wins
    - pHash failures are silently ignored (videos, corrupt files)
    """
    try:
        sha = sha256_of(path)
        if sha in _exact_hashes:
            return   # already known

        _exact_hashes[sha] = (path, pixel_count(path))

        if not skip_phash:
            try:
                ph = phash_of(path)
                for stored_ph, _, _, _ in _phash_store:
                    if (ph - stored_ph) <= PHASH_THRESHOLD:
                        return   # already covered by a near-identical entry
                _phash_store.append((ph, path, pixel_count(path), sha))
            except Exception:
                pass   # pHash unsupported for this file type — skip silently

    except Exception as e:
        log_fn(f"  [index] Warning skipping {path.name}: {e}")


class DuplicateResult:
    """Outcome of a duplicate check for one file."""
    __slots__ = ("is_exact", "is_perceptual", "original", "keep_current",
                 "sha_current", "sha_original", "phash_distance")

    def __init__(
        self,
        is_exact: bool = False,
        is_perceptual: bool = False,
        original: Path | None = None,
        keep_current: bool = False,
        sha_current: str = "",
        sha_original: str = "",
        phash_distance: int = 0,
    ):
        self.is_exact       = is_exact
        self.is_perceptual  = is_perceptual
        self.original       = original
        self.keep_current   = keep_current
        self.sha_current    = sha_current    # SHA-256 of the current file
        self.sha_original   = sha_original   # SHA-256 of the original file
        self.phash_distance = phash_distance # Hamming distance (0 for exact)

    @property
    def is_duplicate(self) -> bool:
        return self.is_exact or self.is_perceptual


def check_duplicate(
    path: Path,
    skip_phash: bool = False,
    log_fn: Callable[[str], None] = print,
) -> DuplicateResult:
    """
    Check whether *path* is a duplicate of something already processed.
    Registers the file in the in-memory stores when it is NOT a duplicate
    (or when it is higher quality than the existing copy).

    Returns a DuplicateResult; callers should inspect .is_duplicate.
    The result also carries SHA-256 hashes and pHash distance for reporting.
    """
    # 1. Exact hash (SHA-256) ────────────────────────────────────────────────
    sha = sha256_of(path)
    if sha in _exact_hashes:
        original, original_px = _exact_hashes[sha]
        sha_orig = sha   # same hash — it's an exact copy
        current_px = pixel_count(path)
        keep_current = current_px > original_px
        if keep_current:
            _exact_hashes[sha] = (path, current_px)
        return DuplicateResult(
            is_exact=True, original=original,
            keep_current=keep_current,
            sha_current=sha, sha_original=sha_orig,
            phash_distance=0,
        )

    # 2. Perceptual hash (pHash) ─────────────────────────────────────────────
    if not skip_phash:
        try:
            ph = phash_of(path)
            current_px = None  # compute lazily, at most once
            for stored_ph, stored_path, stored_px, stored_sha in _phash_store:
                dist = ph - stored_ph
                if dist <= PHASH_THRESHOLD:
                    if current_px is None:
                        current_px = pixel_count(path)
                    keep_current = current_px > stored_px
                    if keep_current:
                        idx = _phash_store.index(
                            (stored_ph, stored_path, stored_px, stored_sha))
                        _phash_store[idx] = (ph, path, current_px, sha)
                    return DuplicateResult(
                        is_perceptual=True,
                        original=stored_path,
                        keep_current=keep_current,
                        sha_current=sha, sha_original=stored_sha,
                        phash_distance=dist,
                    )
            _phash_store.append((ph, path, pixel_count(path), sha))
        except Exception as e:
            log_fn(f"  [pHash] Warning for {path.name}: {e}")

    # Not a duplicate — register
    _exact_hashes[sha] = (path, pixel_count(path))
    return DuplicateResult()


def handle_duplicate(
    path: Path,
    result: DuplicateResult,
    dup_action: str,   # "skip" | "move" | "trash"
    dup_dir: Path,
    dry_run: bool,
    log_fn: Callable[[str], None] = print,
) -> None:
    """
    Apply the chosen action to a duplicate file.

    Actions
    -------
    skip  — log only, leave file in place
    move  — move to dup_dir/
    trash — delete permanently
    """
    kind = "EXACT" if result.is_exact else "NEAR"

    if result.keep_current:
        log_fn(f"  [DUP-{kind}] Higher quality than {result.original.name} "
               f"-> keeping current, original will be actioned instead")
        return

    log_fn(f"  [DUP-{kind}] Duplicate of {result.original.name} "
           f"-> action={dup_action}")

    if dry_run:
        log_fn(f"  [dry-run] would {dup_action}: {path.name}")
        return

    if dup_action == "move":
        dup_dir.mkdir(parents=True, exist_ok=True)
        dest = dup_dir / path.name
        counter = 1
        while dest.exists():
            dest = dup_dir / f"{path.stem}_{counter}{path.suffix}"
            counter += 1
        shutil.move(str(path), dest)
        log_fn(f"  moved to duplicates/ -> {dest.name}")

    elif dup_action == "trash":
        path.unlink()
        log_fn(f"  deleted: {path.name}")

    # "skip" -> do nothing further

