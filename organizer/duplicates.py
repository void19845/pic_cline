from __future__ import annotations
"""organizer.duplicates — exact and perceptual duplicate detection."""

import shutil
from pathlib import Path

from organizer.hashing import sha256_of, phash_of, pixel_count

# ── Module-level state (reset between test runs if needed) ──────────────────
PHASH_THRESHOLD: int = 8          # Hamming distance; 0=identical ≤10=near-dup

_exact_hashes: dict[str, Path] = {}   # sha256 → first-seen path
_phash_store:  list[tuple]     = []   # [(phash_obj, path), …]


def reset_stores() -> None:
    """Clear in-memory duplicate stores (useful for tests)."""
    _exact_hashes.clear()
    _phash_store.clear()


class DuplicateResult:
    """Outcome of a duplicate check for one file."""
    __slots__ = ("is_exact", "is_perceptual", "original", "keep_current")

    def __init__(
        self,
        is_exact: bool = False,
        is_perceptual: bool = False,
        original: Path | None = None,
        keep_current: bool = False,
    ):
        self.is_exact      = is_exact
        self.is_perceptual = is_perceptual
        self.original      = original       # path of the already-seen file
        self.keep_current  = keep_current   # True → current file is higher quality

    @property
    def is_duplicate(self) -> bool:
        return self.is_exact or self.is_perceptual


def check_duplicate(path: Path, skip_phash: bool = False) -> DuplicateResult:
    """
    Check whether *path* is a duplicate of something already processed.
    Registers the file in the in-memory stores when it is NOT a duplicate
    (or when it is higher quality than the existing copy).

    Returns a DuplicateResult; callers should inspect .is_duplicate.
    """
    # 1. Exact hash (SHA-256) ────────────────────────────────────────────────
    sha = sha256_of(path)
    if sha in _exact_hashes:
        original = _exact_hashes[sha]
        keep_current = pixel_count(path) > pixel_count(original)
        if keep_current:
            _exact_hashes[sha] = path
        return DuplicateResult(is_exact=True, original=original,
                               keep_current=keep_current)

    # 2. Perceptual hash (pHash) ─────────────────────────────────────────────
    if not skip_phash:
        try:
            ph = phash_of(path)
            for stored_ph, stored_path in _phash_store:
                if (ph - stored_ph) <= PHASH_THRESHOLD:
                    keep_current = pixel_count(path) > pixel_count(stored_path)
                    if keep_current:
                        idx = _phash_store.index((stored_ph, stored_path))
                        _phash_store[idx] = (ph, path)
                    return DuplicateResult(
                        is_perceptual=True,
                        original=stored_path,
                        keep_current=keep_current,
                    )
            _phash_store.append((ph, path))
        except Exception as e:
            print(f"  [pHash] Warning for {path.name}: {e}")

    # Not a duplicate — register
    _exact_hashes[sha] = path
    return DuplicateResult()


def handle_duplicate(
    path: Path,
    result: DuplicateResult,
    dup_action: str,   # "skip" | "move" | "trash"
    dup_dir: Path,
    dry_run: bool,
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
        print(f"  [DUP-{kind}] Higher quality than {result.original.name} "
              f"→ keeping current, original will be actioned instead")
        return

    print(f"  [DUP-{kind}] Duplicate of {result.original.name} "
          f"→ action={dup_action}")

    if dry_run:
        print(f"  [dry-run] would {dup_action}: {path.name}")
        return

    if dup_action == "move":
        dup_dir.mkdir(parents=True, exist_ok=True)
        dest = dup_dir / path.name
        counter = 1
        while dest.exists():
            dest = dup_dir / f"{path.stem}_{counter}{path.suffix}"
            counter += 1
        shutil.move(str(path), dest)
        print(f"  moved to duplicates/ → {dest.name}")

    elif dup_action == "trash":
        path.unlink()
        print(f"  deleted: {path.name}")

    # "skip" → do nothing further
