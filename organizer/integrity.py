from __future__ import annotations
"""organizer.integrity — post-move SHA-256 verification."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from .hashing import sha256_of


class IntegrityStatus(str, Enum):
    OK        = "OK"
    MISSING   = "MISSING"
    CORRUPTED = "CORRUPTED"
    SKIPPED   = "SKIPPED"


@dataclass
class IntegrityRecord:
    source:      str
    destination: str
    source_hash: str
    dest_hash:   str | None
    status:      IntegrityStatus
    size_src:    int = 0
    size_dst:    int = 0


def verify_move(
    src_path: Path,
    dst_path: Path,
    src_hash: str,
) -> IntegrityRecord:
    """
    Compare *src_hash* against a fresh hash of *dst_path*.

    Returns
    -------
    IntegrityRecord with status:
      OK        — hashes match
      MISSING   — dst_path does not exist
      CORRUPTED — dst_path exists but hash differs
    """
    if not dst_path.exists():
        return IntegrityRecord(
            source=str(src_path), destination=str(dst_path),
            source_hash=src_hash, dest_hash=None,
            status=IntegrityStatus.MISSING,
        )

    dst_hash = sha256_of(dst_path)
    return IntegrityRecord(
        source=str(src_path), destination=str(dst_path),
        source_hash=src_hash, dest_hash=dst_hash,
        status=IntegrityStatus.OK if dst_hash == src_hash else IntegrityStatus.CORRUPTED,
        size_dst=dst_path.stat().st_size,
    )


def write_integrity_report(
    vault_root: Path,
    records: list[IntegrityRecord],
    dry_run: bool,
    log_fn=print,
) -> None:
    """Write ``integrity_report.md`` to vault root."""
    ts        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ok        = sum(1 for r in records if r.status == IntegrityStatus.OK)
    missing   = sum(1 for r in records if r.status == IntegrityStatus.MISSING)
    corrupted = sum(1 for r in records if r.status == IntegrityStatus.CORRUPTED)
    skipped   = sum(1 for r in records if r.status == IntegrityStatus.SKIPPED)

    lines = [
        "# Integrity report", "",
        f"Generated: {ts}", "",
        "| Status | Count |",
        "|--------|-------|",
        f"| [OK] OK | {ok} |",
        f"| [??] Skipped | {skipped} |",
        f"| [!!] Missing | {missing} |",
        f"| [!!] Corrupted | {corrupted} |", "",
    ]

    problems = [r for r in records
                if r.status in (IntegrityStatus.MISSING, IntegrityStatus.CORRUPTED)]
    if problems:
        lines += [
            "## Problems", "",
            "| Status | File | Source hash | Dest hash |",
            "|--------|------|-------------|-----------|",
        ]
        for r in problems:
            dh = (r.dest_hash or "—")[:12] + "..."
            sh = r.source_hash[:12] + "..."
            lines.append(
                f"| {r.status} | {Path(r.destination).name} | `{sh}` | `{dh}` |"
            )
        lines.append("")

    lines += [
        "## All records", "",
        "| Status | File | SHA-256 |",
        "|--------|------|---------|",
    ]
    icons = {"OK": "[OK]", "MISSING": "[!!]", "CORRUPTED": "[!!]", "SKIPPED": "[??]"}
    for r in records:
        icon = icons.get(r.status, "?")
        lines.append(
            f"| {icon} {r.status} | {Path(r.destination).name} "
            f"| `{r.source_hash[:12]}...` |"
        )

    report_path = vault_root / "integrity_report.md"
    if not dry_run:
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log_fn(f"\nIntegrity report -> {report_path}")
    else:
        log_fn(f"\n[dry-run] would write integrity report -> {report_path}")
