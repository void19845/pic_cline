
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from .base import register_entity_type
from .media import MediaEntity

@register_entity_type
@dataclass
class PhotoNote(MediaEntity):
    ENTITY_TYPE: str = field(default="photo", init=False, repr=False)
    VAULT_SUBPATH: str = field(default="photo-notes", init=False, repr=False)
    date_taken: str = ""; year: "int | None" = None; month: str = ""
    city: str = ""; country: str = ""
    latitude: "float | None" = None; longitude: "float | None" = None
    camera_make: str = ""; camera_model: str = ""
    focal_length: "float | None" = None; aperture: "float | None" = None
    shutter: str = ""; iso: "int | None" = None
    width: "int | None" = None; height: "int | None" = None
    ai_tags: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)

    def _collect_errors(self):
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
            "date_taken": self.date_taken or None, "year": self.year,
            "month": self.month or None, "city": self.city or None,
            "country": self.country or None, "latitude": self.latitude,
            "longitude": self.longitude, "camera_make": self.camera_make or None,
            "camera_model": self.camera_model or None, "focal_length": self.focal_length,
            "aperture": self.aperture, "shutter": self.shutter or None,
            "iso": self.iso, "width": self.width, "height": self.height,
            "ai_tags": self.ai_tags, "people": self.people,
        })
        return data

    def note_body(self) -> str:
        lines = [f"![[{self.file_path}]]", ""]
        if self.city: lines.append(f"**Location:** [[{self.city}]]")
        if self.people: lines.append(f"**People:** {', '.join(f'[[{p}]]' for p in self.people)}")
        if self.ai_tags: lines.append(f"**Scene:** {', '.join(self.ai_tags)}")
        lines += ["", "---", "", "```dataview", "TABLE date_taken, city, people",
                  'FROM "photo-notes"']
        if self.city: lines.append(f'WHERE city = "{self.city}"')
        lines += ["SORT date_taken DESC", "LIMIT 10", "```"]
        return "\n".join(lines)

    def vault_path_components(self) -> list[str]:
        parts = []
        if self.year: parts.append(str(self.year))
        if self.month: parts.append(self.month)
        parts.append(self.city if self.city else "no_location")
        return parts
