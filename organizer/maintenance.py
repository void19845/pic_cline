from __future__ import annotations
"""organizer.maintenance — vault housekeeping utilities."""

import json
import re
from pathlib import Path

from organizer.metadata import SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS


# ── Face label renaming ──────────────────────────────────────────────────────

def apply_face_renames(vault_root: Path, notes_dir: Path) -> int:
    """
    Replace auto-generated ``person_XX`` labels in all notes with human names
    defined in ``<vault_root>/face_labels.json``.

    The JSON file maps auto-label → human name, e.g.::

        {
          "person_00": "Alice",
          "person_01": "Bob",
          "person_02": "person_02"   ← unchanged, will be skipped
        }

    Only entries where the value differs from the key are applied.

    Returns the number of notes updated.
    """
    labels_file = vault_root / "face_labels.json"

    if not labels_file.exists():
        print("No face_labels.json found — run the organizer first.")
        return 0

    try:
        labels: dict[str, str] = json.loads(
            labels_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Could not read face_labels.json: {e}")
        return 0

    changes = {auto: human for auto, human in labels.items()
               if auto != human and human.strip()}

    if not changes:
        print("No renames defined — edit face_labels.json so values differ "
              "from keys, e.g.  \"person_00\": \"Alice\"")
        return 0

    print(f"Applying {len(changes)} rename(s):")
    for auto, human in changes.items():
        print(f"  {auto} -> {human}")

    updated = 0
    for md in sorted(notes_dir.glob("*.md")):
        original = md.read_text(encoding="utf-8")
        text = original

        for auto_label, human_name in changes.items():
            # Wikilinks:  [[person_00]]  →  [[Alice]]
            text = text.replace(f"[[{auto_label}]]", f"[[{human_name}]]")
            # YAML list entries (various positions):
            #   [person_00, ...]  →  [Alice, ...]
            #   [..., person_00]  →  [..., Alice]
            #   [..., person_00, ...]
            text = re.sub(
                r'(?<=[\[,\s])' + re.escape(auto_label) + r'(?=[\],\s])',
                human_name,
                text,
            )

        if text != original:
            md.write_text(text, encoding="utf-8")
            updated += 1
            print(f"  updated: {md.name}")

    print(f"\nDone — {updated} note(s) updated.")
    return updated


# ── Orphan note cleanup ──────────────────────────────────────────────────────

_EMBED_RE = re.compile(r'!\[\[([^\]]+)\]\]')


def cleanup_orphan_notes(
    notes_dir: Path,
    vault_root: Path,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Delete ``.md`` notes whose embedded media file no longer exists.

    A note is **fully orphaned** when every ``![[...]]`` embed it contains
    points to a missing file — the note is then deleted (or previewed with
    ``dry_run=True``).

    A note is **partially orphaned** when only some embeds are broken — it is
    kept but a warning is printed.

    Returns ``(orphans_found, orphans_deleted)``.
    """
    if not notes_dir.exists():
        print("Notes directory does not exist — nothing to clean up.")
        return 0, 0

    all_media_names: set[str] = {
        p.name.lower()
        for p in vault_root.rglob("*")
        if p.suffix.lower() in (SUPPORTED_EXTENSIONS | VIDEO_EXTENSIONS)
    }

    orphans_found   = 0
    orphans_deleted = 0

    for md in sorted(notes_dir.glob("*.md")):
        text   = md.read_text(encoding="utf-8")
        embeds = _EMBED_RE.findall(text)

        if not embeds:
            continue   # no media embed → keep (might be an index/hub note)

        broken = [
            embed for embed in embeds
            if not (vault_root / embed).exists()
            and Path(embed).name.lower() not in all_media_names
        ]

        if len(broken) == len(embeds):
            # All embeds broken → fully orphaned
            orphans_found += 1
            if dry_run:
                print(f"  [dry-run] would delete: {md.name}")
                print(f"            missing embed(s): {', '.join(broken)}")
            else:
                md.unlink()
                orphans_deleted += 1
                print(f"  [cleanup] deleted: {md.name}")
                print(f"            missing embed(s): {', '.join(broken)}")

        elif broken:
            # Some embeds broken → warn and keep
            print(f"  [cleanup] partial orphan (kept): {md.name}")
            print(f"            broken embed(s): {', '.join(broken)}")

    verb = "would delete" if dry_run else "deleted"
    print(f"\nOrphan cleanup: {orphans_found} fully orphaned note(s), "
          f"{orphans_deleted} {verb}.")
    return orphans_found, orphans_deleted
