from __future__ import annotations
"""
organizer.dup_report
====================
Markdown-based storage for duplicate pairs.

Two files live in the vault root:

  duplicates_report.md   — pending pairs (status = pending)
  duplicates_archive.md  — resolved pairs (append-only log)

Record format (one row per pair in a Markdown table)
-----------------------------------------------------
Each row encodes all fields needed to:
  • display the pair in the reviewer
  • identify it uniquely across runs (composite key)
  • resolve the current file path after moves

Composite key (used for merge / deduplication)
-----------------------------------------------
  sha_original + sha_duplicate + path_original
  Robust against renames and near-identical hash collisions.

Merge strategy (called at the start of every sort run)
------------------------------------------------------
  1. Read existing pending pairs from duplicates_report.md
  2. For each newly detected pair:
       - If key already exists -> update fields that may have changed
         (resolved paths, sizes) but keep status = pending
       - If key is new -> append
  3. Write the merged table back to duplicates_report.md
  4. Resolved pairs are moved to duplicates_archive.md when the
     reviewer makes a decision, never touched again.

Statuses
--------
  pending            — no decision taken yet
  reviewed-keep-original
  reviewed-keep-duplicate
  reviewed-keep-both
  (skipped pairs remain pending)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

REPORT_FILE  = "duplicates_report.md"
ARCHIVE_FILE = "duplicates_archive.md"

_STATUS_PENDING = "pending"


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class DupPair:
    """A single duplicate pair record."""

    # Composite key fields (never change after first detection)
    sha_original:   str
    sha_duplicate:  str
    path_original:  str          # original source path at detection time

    # Descriptive fields (may update on re-scan)
    path_duplicate: str
    kind:           str          # "exact" | "perceptual"
    phash_distance: int          # 0 for exact, 1-20 for perceptual
    res_original:   str          # "3024x4032" or "?"
    res_duplicate:  str
    size_original:  str          # "4.2 MB"
    size_duplicate: str
    detected_at:    str          # ISO date

    # Resolved vault paths (updated each run)
    vault_original:  str         # path after move, relative to vault
    vault_duplicate: str

    # Decision
    status: str = _STATUS_PENDING

    @property
    def key(self) -> str:
        """Stable composite key for merge deduplication."""
        return f"{self.sha_original}:{self.sha_duplicate}:{self.path_original}"

    @property
    def is_pending(self) -> bool:
        return self.status == _STATUS_PENDING

    @property
    def is_resolved(self) -> bool:
        return not self.is_pending


# ── Markdown serialisation ────────────────────────────────────────────────────

# Column order in the Markdown table
_COLUMNS = [
    "key",
    "sha_original", "sha_duplicate", "path_original", "path_duplicate",
    "kind", "phash_distance",
    "res_original", "res_duplicate",
    "size_original", "size_duplicate",
    "detected_at",
    "vault_original", "vault_duplicate",
    "status",
]

_HEADER = "| " + " | ".join(_COLUMNS) + " |"
_SEP    = "| " + " | ".join("---" for _ in _COLUMNS) + " |"


def _esc(s: str) -> str:
    """Escape pipe characters so the value doesn't break the table."""
    return s.replace("|", "\\|")


def _unesc(s: str) -> str:
    return s.replace("\\|", "|")


def _row(pair: DupPair) -> str:
    vals = [
        pair.key,
        pair.sha_original[:16], pair.sha_duplicate[:16],
        _esc(pair.path_original), _esc(pair.path_duplicate),
        pair.kind, str(pair.phash_distance),
        pair.res_original, pair.res_duplicate,
        pair.size_original, pair.size_duplicate,
        pair.detected_at,
        _esc(pair.vault_original), _esc(pair.vault_duplicate),
        pair.status,
    ]
    return "| " + " | ".join(vals) + " |"


def _parse_row(line: str) -> Optional[DupPair]:
    """Parse one Markdown table row into a DupPair. Returns None on failure."""
    line = line.strip()
    if not line.startswith("|") or line.startswith("| key") or set(line.replace("|","").replace("-","").replace(" ","")) == set():
        return None
    cells = [_unesc(c.strip()) for c in line.split("|")[1:-1]]
    if len(cells) != len(_COLUMNS):
        return None
    try:
        c = cells
        return DupPair(
            sha_original   = c[1],
            sha_duplicate  = c[2],
            path_original  = c[3],
            path_duplicate = c[4],
            kind           = c[5],
            phash_distance = int(c[6]) if c[6].isdigit() else 0,
            res_original   = c[7],
            res_duplicate  = c[8],
            size_original  = c[9],
            size_duplicate = c[10],
            detected_at    = c[11],
            vault_original = c[12],
            vault_duplicate= c[13],
            status         = c[14],
        )
    except Exception:
        return None


def _pairs_to_md(pairs: list[DupPair], title: str, subtitle: str = "") -> str:
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {title}",
        "",
        f"> Last updated: {ts}",
        subtitle,
        "",
        _HEADER,
        _SEP,
    ]
    for p in pairs:
        lines.append(_row(p))
    lines.append("")
    return "\n".join(lines)


def _read_pairs(path: Path) -> list[DupPair]:
    """Read all DupPair rows from a Markdown report file."""
    if not path.exists():
        return []
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        pair = _parse_row(line)
        if pair is not None:
            pairs.append(pair)
    return pairs


# ── Public API ────────────────────────────────────────────────────────────────

def merge_and_save(
    vault_root: Path,
    new_pairs: list[DupPair],
    dry_run: bool = False,
    log_fn=print,
) -> None:
    """
    Merge *new_pairs* into the existing ``duplicates_report.md``.

    Algorithm
    ---------
    1. Load existing pending pairs (keyed by composite key).
    2. For each new pair:
         • If key already exists: update mutable fields
           (resolved paths, sizes, phash_distance) — keep status.
         • If key is new: add with status = pending.
    3. Write merged pending list back to duplicates_report.md.

    Resolved pairs in the archive are never touched.
    """
    report_path = vault_root / REPORT_FILE

    # Load existing pending pairs as {key: DupPair}
    existing: dict[str, DupPair] = {p.key: p for p in _read_pairs(report_path)}

    merged_count = 0
    added_count  = 0

    for np in new_pairs:
        if np.key in existing:
            old = existing[np.key]
            # Update mutable fields but preserve the decision status
            old.vault_original  = np.vault_original
            old.vault_duplicate = np.vault_duplicate
            old.res_original    = np.res_original
            old.res_duplicate   = np.res_duplicate
            old.size_original   = np.size_original
            old.size_duplicate  = np.size_duplicate
            old.phash_distance  = np.phash_distance
            merged_count += 1
        else:
            existing[np.key] = np
            added_count += 1

    pending = [p for p in existing.values() if p.is_pending]
    pending.sort(key=lambda p: p.detected_at, reverse=True)

    subtitle = (f"> {len(pending)} pending pair(s)  -  "
                f"{added_count} new  -  {merged_count} updated this run")

    if dry_run:
        log_fn(f"\n[dry-run] would write {REPORT_FILE} "
               f"({len(pending)} pending, {added_count} new, {merged_count} updated)")
        return

    content = _pairs_to_md(pending, "Duplicate pairs — pending review", subtitle)
    report_path.write_text(content, encoding="utf-8")
    log_fn(f"\nDuplicate report -> {report_path} "
           f"({len(pending)} pending, {added_count} new, {merged_count} updated)")


def resolve_pair(
    vault_root: Path,
    key: str,
    status: str,
    dry_run: bool = False,
    log_fn=print,
) -> bool:
    """
    Move a pending pair from duplicates_report.md to duplicates_archive.md.

    Returns True if the pair was found and moved.
    """
    report_path  = vault_root / REPORT_FILE
    archive_path = vault_root / ARCHIVE_FILE

    pairs = _read_pairs(report_path)
    target = next((p for p in pairs if p.key == key), None)
    if target is None:
        return False

    target.status = status

    remaining = [p for p in pairs if p.key != key]

    if dry_run:
        log_fn(f"  [dry-run] would resolve pair -> {status}")
        return True

    # Rewrite pending report without this pair
    subtitle = f"> {len(remaining)} pending pair(s)"
    report_path.write_text(
        _pairs_to_md(remaining, "Duplicate pairs — pending review", subtitle),
        encoding="utf-8",
    )

    # Append to archive (create if needed)
    if archive_path.exists():
        archive_pairs = _read_pairs(archive_path)
    else:
        archive_pairs = []
    archive_pairs.append(target)
    archive_path.write_text(
        _pairs_to_md(archive_pairs, "Duplicate pairs — archive (resolved)", ""),
        encoding="utf-8",
    )

    return True


def load_pending(vault_root: Path) -> list[DupPair]:
    """Return all pending pairs from duplicates_report.md."""
    return [p for p in _read_pairs(vault_root / REPORT_FILE) if p.is_pending]


# ── Helper: build a DupPair from detection data ───────────────────────────────

def _fmt_size(path: Path) -> str:
    try:
        b = path.stat().st_size
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except Exception:
        return "?"


def _fmt_res(path: Path) -> str:
    try:
        from PIL import Image
        with Image.open(path) as img:
            return f"{img.width}x{img.height}"
    except Exception:
        return "?"


def build_dup_pair(
    original_path: Path,
    duplicate_path: Path,
    sha_original: str,
    sha_duplicate: str,
    kind: str,
    phash_distance: int,
    vault_root: Path,
) -> DupPair:
    """
    Construct a DupPair from detection-time data.
    Resolved vault paths are computed relative to vault_root when possible.
    """
    def _vault_rel(p: Path) -> str:
        try:
            return str(p.relative_to(vault_root)).replace("\\", "/")
        except ValueError:
            return str(p)

    return DupPair(
        sha_original   = sha_original,
        sha_duplicate  = sha_duplicate,
        path_original  = str(original_path),
        path_duplicate = str(duplicate_path),
        kind           = kind,
        phash_distance = phash_distance,
        res_original   = _fmt_res(original_path),
        res_duplicate  = _fmt_res(duplicate_path),
        size_original  = _fmt_size(original_path),
        size_duplicate = _fmt_size(duplicate_path),
        detected_at    = datetime.now().strftime("%Y-%m-%d %H:%M"),
        vault_original  = _vault_rel(original_path),
        vault_duplicate = _vault_rel(duplicate_path),
        status         = _STATUS_PENDING,
    )
