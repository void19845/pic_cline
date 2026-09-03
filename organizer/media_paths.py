from __future__ import annotations
"""
organizer.media_paths — physical media file placement.

Replaces the old organizer/notes.py. Note *generation* (frontmatter +
body) now lives entirely in PhotoNote/VideoNote (organizer/models.py,
core.PhotoNote) — this module only decides where the media FILE itself
goes on disk, which is independent of obsidian_core (core only owns
the .md notes, never the underlying media).
"""

from pathlib import Path

from organizer.metadata import _safe, VIDEO_EXTENSIONS


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def destination_path(
    output_root: Path,
    meta: dict,
    city: str | None,
    filename: str,
) -> Path:
    """
    Build the destination path for a media file:
      <output_root>/<year>/<MM-MonthName>/<city_or_no_location>/<filename>
    """
    date_obj = meta.get("date")
    year  = date_obj.strftime("%Y")    if date_obj else "unknown_year"
    month = date_obj.strftime("%m-%B") if date_obj else "unknown_month"
    place = _safe(city) if city else "no_location"
    return output_root / year / month / place / filename
