from __future__ import annotations
"""
organizer.models — Photo Organizer entities on top of obsidian_core.

`core/` is treated as sacred: never modified, only imported and extended
via its registration pattern (see core/README's "Adding a Custom Entity
Type" example — VideoNote below follows that pattern exactly).

PhotoNote already lives in core and is used as-is. VideoNote does not
exist in core (core only ships Photo/Track), so it is defined here and
registered the same way core's own docs show.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core import MediaEntity, PhotoNote, register_entity_type
from core import generate_id, month_label_from_iso, slugify, to_iso, year_from_iso


@register_entity_type
@dataclass
class VideoNote(MediaEntity):
    """
    Photo Organizer entity for video files.

    VAULT_SUBPATH is deliberately the SAME as PhotoNote ("photo-notes"):
    a camera roll's photos and videos are one story per trip/event, and
    co-locating them means a single Dataview query over "photo-notes"
    sees both (filter with `type` when you want just one).
    """
    ENTITY_TYPE: str = field(default="video", init=False, repr=False)
    VAULT_SUBPATH: str = field(default="photo-notes", init=False, repr=False)

    title: str = ""
    date_taken: str = ""
    year: int | None = None
    month: str = ""                 # "08-August"

    city: str = ""
    country: str = ""
    latitude: float | None = None   # validated: -90 to 90
    longitude: float | None = None  # validated: -180 to 180

    camera_make: str = ""
    camera_model: str = ""
    duration: float | None = None   # seconds
    duration_fmt: str = ""          # "1h 23m 45s"
    width: int | None = None
    height: int | None = None
    codec: str = ""

    def _collect_errors(self) -> list[str]:
        errors = super()._collect_errors()
        if self.year is not None and not (1800 <= self.year <= 2100):
            errors.append(f"'year' out of plausible range: {self.year}")
        if self.latitude is not None and not (-90 <= self.latitude <= 90):
            errors.append(f"'latitude' out of range: {self.latitude}")
        if self.longitude is not None and not (-180 <= self.longitude <= 180):
            errors.append(f"'longitude' out of range: {self.longitude}")
        return errors

    def to_frontmatter(self) -> dict[str, Any]:
        data = super().to_frontmatter()
        data.update({
            "title": self.title or None,
            "date_taken": self.date_taken or None,
            "year": self.year,
            "month": self.month or None,
            "city": self.city or None,
            "country": self.country or None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "camera_make": self.camera_make or None,
            "camera_model": self.camera_model or None,
            "duration": self.duration,
            "duration_fmt": self.duration_fmt or None,
            "width": self.width,
            "height": self.height,
            "codec": self.codec or None,
        })
        return data

    def note_body(self) -> str:
        lines = [f"![[{self.file_path}]]", ""]

        loc_links = []
        if self.city:
            loc_links.append(f"[[{self.city}]]")
        if self.country and self.country != self.city:
            loc_links.append(f"[[{self.country}]]")
        if self.month:
            loc_links.append(f"[[{self.month}]]")
        if loc_links:
            lines.append(" · ".join(loc_links))

        if self.tags:
            lines.append(" ".join(f"#{t}" for t in self.tags))

        tech = []
        if self.duration_fmt:
            tech.append(self.duration_fmt)
        if self.width and self.height:
            tech.append(f"{self.width}×{self.height}")
        cam = f"{self.camera_make} {self.camera_model}".strip()
        if cam:
            tech.append(cam)
        if tech:
            lines += ["", " · ".join(tech)]

        where = 'type = "video"'
        if self.city:
            where += f' AND city = "{self.city}"'
        lines += ["", "---", "", "```dataview",
                  "TABLE date_taken, city, duration_fmt",
                  'FROM "photo-notes"', f"WHERE {where}",
                  "SORT date_taken DESC", "LIMIT 10", "```"]
        return "\n".join(lines)

    def vault_path_components(self) -> list[str]:
        parts = []
        if self.year:
            parts.append(str(self.year))
        if self.month:
            parts.append(self.month)
        parts.append(self.city if self.city else "no_location")
        return parts


# ── Factories: pipeline data (dicts, WorkerResult fields) -> entity ──────────
#
# Design choice: the id is generated from the already-computed SHA-256 of
# the file content (`src_hash`), not from the filename or path. Same photo
# reprocessed under a different name -> same id -> vault.upsert() updates
# the existing note instead of creating a duplicate. This reuses the hash
# that check_duplicate()/verify_move() already compute — no extra I/O, and
# it's the same "one hash, multiple uses" principle already applied in
# Document Parser.

def build_photo_note(
    item: Path,
    item_rel: Path,
    meta: dict,
    tags: list[str],
    people: list[str],
    city: str | None,
    country: str | None,
    src_hash: str,
    src_size: int,
) -> PhotoNote:
    date_iso = to_iso(meta.get("date"))
    fm_tags = [slugify(city.lower())] if city else []

    return PhotoNote(
        id=generate_id("photo", src_hash),
        file_path=str(item_rel).replace("\\", "/"),
        file_size=src_size,
        sha256=src_hash,
        date_added=to_iso(datetime.now()),
        tags=fm_tags,
        date_taken=date_iso or "",
        year=year_from_iso(date_iso),
        month=month_label_from_iso(date_iso) or "",
        city=city or "",
        country=country or "",
        latitude=meta.get("lat"),
        longitude=meta.get("lon"),
        camera_make=meta.get("camera_make") or "",
        camera_model=meta.get("camera_model") or "",
        focal_length=meta.get("focal_length"),
        aperture=meta.get("aperture"),
        shutter=meta.get("shutter") or "",
        iso=meta.get("iso"),
        width=meta.get("width"),
        height=meta.get("height"),
        ai_tags=tags,
        people=people,
    )


def build_video_note(
    item: Path,
    item_rel: Path,
    meta: dict,
    city: str | None,
    country: str | None,
    src_hash: str,
    src_size: int,
    duration_fmt: str = "",
) -> VideoNote:
    date_iso = to_iso(meta.get("date"))
    fm_tags = ["video"]
    if city:
        fm_tags.insert(0, slugify(city.lower()))

    return VideoNote(
        id=generate_id("video", src_hash),
        file_path=str(item_rel).replace("\\", "/"),
        file_size=src_size,
        sha256=src_hash,
        date_added=to_iso(datetime.now()),
        tags=fm_tags,
        title=item.stem,
        date_taken=date_iso or "",
        year=year_from_iso(date_iso),
        month=month_label_from_iso(date_iso) or "",
        city=city or "",
        country=country or "",
        latitude=meta.get("lat"),
        longitude=meta.get("lon"),
        camera_make=meta.get("camera_make") or "",
        camera_model=meta.get("camera_model") or "",
        duration=meta.get("duration_s"),
        duration_fmt=duration_fmt,
        width=meta.get("width"),
        height=meta.get("height"),
        codec=meta.get("codec") or "",
    )
