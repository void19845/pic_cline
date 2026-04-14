from __future__ import annotations
"""organizer.notes — Obsidian Markdown note generation."""

from pathlib import Path

from organizer.metadata import _safe, VIDEO_EXTENSIONS, format_duration


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def destination_path(
    output_root: Path,
    meta: dict,
    city: str | None,
    filename: str,
) -> Path:
    """
    Build the destination path:
      <output_root>/<year>/<MM-MonthName>/<city_or_no_location>/<filename>
    """
    date_obj = meta.get("date")
    year  = date_obj.strftime("%Y")    if date_obj else "unknown_year"
    month = date_obj.strftime("%m-%B") if date_obj else "unknown_month"
    place = _safe(city) if city else "no_location"
    return output_root / year / month / place / filename


def build_obsidian_note(
    photo_rel_path: str,
    exif: dict,
    tags: list[str],
    people: list[str],
    city: str | None,
    country: str | None,
) -> str:
    """
    Generate Obsidian Markdown for a photo.

    Frontmatter
    -----------
    title, date, location, country, tags, people,
    camera, focal_length, aperture, shutter, iso, dimensions, latitude, longitude

    Body
    ----
    ![[embed]], wikilinks (location · date · people), hashtags, camera line
    """
    date_obj  = exif.get("date")
    date_str  = date_obj.strftime("%Y-%m-%d") if date_obj else "unknown"
    month_str = date_obj.strftime("%Y-%m")     if date_obj else "unknown"
    loc_str   = ", ".join(filter(None, [city, country])) or "unknown"

    fm_tags = list(tags)
    if city:
        fm_tags.insert(0, _safe(city.lower().replace(" ", "-")))

    lines = [
        "---",
        f'title: "{Path(photo_rel_path).stem}"',
        f"date: {date_str}",
        f'location: "{loc_str}"',
    ]
    if country:
        lines.append(f'country: "{country}"')
    if fm_tags:
        lines.append(f"tags: [{', '.join(fm_tags)}]")
    if people:
        lines.append(f"people: [{', '.join(people)}]")

    make  = exif.get("camera_make")  or ""
    model = exif.get("camera_model") or ""
    cam   = f"{make} {model}".strip() or None
    if cam:
        lines.append(f'camera: "{cam}"')
    if exif.get("focal_length"):
        lines.append(f'focal_length: "{exif["focal_length"]:.0f}mm"')
    if exif.get("aperture"):
        lines.append(f'aperture: "f/{exif["aperture"]:.1f}"')
    if exif.get("shutter"):
        lines.append(f'shutter: "{exif["shutter"]}"')
    if exif.get("iso"):
        lines.append(f"iso: {exif['iso']}")
    if exif.get("lat") and exif.get("lon"):
        lines.append(f"latitude: {exif['lat']:.6f}")
        lines.append(f"longitude: {exif['lon']:.6f}")
    if exif.get("width") and exif.get("height"):
        lines.append(f'dimensions: "{exif["width"]}x{exif["height"]}"')
    lines.append("---")

    body = [f"![[{photo_rel_path}]]", ""]

    loc_links = []
    if city:
        loc_links.append(f"[[{_safe(city)}]]")
    if country and country != city:
        loc_links.append(f"[[{_safe(country)}]]")
    loc_links.append(f"[[{month_str}]]")
    body.append(" · ".join(loc_links))

    if people:
        body.append(" ".join(f"[[{p}]]" for p in people))
    if fm_tags:
        body.append(" ".join(f"#{t}" for t in fm_tags))

    tech = [cam] if cam else []
    if exif.get("aperture"):
        tech.append(f"f/{exif['aperture']:.1f}")
    if exif.get("shutter"):
        tech.append(exif["shutter"])
    if exif.get("iso"):
        tech.append(f"ISO {exif['iso']}")
    if tech:
        body += ["", " · ".join(tech)]

    return "\n".join(lines) + "\n\n" + "\n".join(body) + "\n"


def build_video_note(
    video_rel_path: str,
    meta: dict,
    city: str | None,
    country: str | None,
) -> str:
    """
    Generate Obsidian Markdown for a video file.

    Frontmatter
    -----------
    title, date, location, country, type, tags,
    duration, resolution, codec, camera, latitude, longitude

    Body
    ----
    ![[embed]], wikilinks, hashtags, technical detail line
    """
    date_obj  = meta.get("date")
    date_str  = date_obj.strftime("%Y-%m-%d") if date_obj else "unknown"
    month_str = date_obj.strftime("%Y-%m")     if date_obj else "unknown"
    loc_str   = ", ".join(filter(None, [city, country])) or "unknown"

    fm_tags = []
    if city:
        fm_tags.append(_safe(city.lower().replace(" ", "-")))
    fm_tags.append("video")

    lines = [
        "---",
        f'title: "{Path(video_rel_path).stem}"',
        f"date: {date_str}",
        f'location: "{loc_str}"',
        "type: video",
    ]
    if country:
        lines.append(f'country: "{country}"')
    lines.append(f"tags: [{', '.join(fm_tags)}]")
    if meta.get("duration_s") is not None:
        lines.append(f'duration: "{format_duration(meta["duration_s"])}"')
    if meta.get("width") and meta.get("height"):
        lines.append(f'resolution: "{meta["width"]}x{meta["height"]}"')
    if meta.get("codec"):
        lines.append(f'codec: "{meta["codec"]}"')
    make  = meta.get("camera_make")  or ""
    model = meta.get("camera_model") or ""
    cam   = f"{make} {model}".strip()
    if cam:
        lines.append(f'camera: "{cam}"')
    if meta.get("lat") and meta.get("lon"):
        lines.append(f"latitude: {meta['lat']:.6f}")
        lines.append(f"longitude: {meta['lon']:.6f}")
    lines.append("---")

    body = [f"![[{video_rel_path}]]", ""]

    loc_links = []
    if city:
        loc_links.append(f"[[{_safe(city)}]]")
    if country and country != city:
        loc_links.append(f"[[{_safe(country)}]]")
    loc_links.append(f"[[{month_str}]]")
    body.append(" · ".join(loc_links))
    body.append(" ".join(f"#{t}" for t in fm_tags))

    tech = []
    if meta.get("duration_s") is not None:
        tech.append(format_duration(meta["duration_s"]))
    if meta.get("width") and meta.get("height"):
        tech.append(f"{meta['width']}×{meta['height']}")
    if cam:
        tech.append(cam)
    if tech:
        body += ["", " · ".join(tech)]

    return "\n".join(lines) + "\n\n" + "\n".join(body) + "\n"
