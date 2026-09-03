
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any
from .base import register_entity_type
from .media import MediaEntity

def _valid_camelot(code: str) -> bool:
    return bool(re.fullmatch(r"(1[0-2]|[1-9])[AB]", code))

@register_entity_type
@dataclass
class TrackNote(MediaEntity):
    ENTITY_TYPE: str = field(default="track", init=False, repr=False)
    VAULT_SUBPATH: str = field(default="Music", init=False, repr=False)
    title: str = ""; artist: str = ""; album: str = ""; genre: str = ""
    year: "int | None" = None; isrc: str = ""
    bpm: "float | None" = None; key: str = ""; camelot: str = ""
    duration: "float | None" = None; duration_fmt: str = ""
    cue_points: list[float] = field(default_factory=list)
    loops: list[dict] = field(default_factory=list)

    def _collect_errors(self):
        errors = super()._collect_errors()
        if not self.title: errors.append("'title' is required for track entities")
        if not self.artist: errors.append("'artist' is required for track entities")
        if self.bpm is not None and not (20 <= self.bpm <= 300):
            errors.append(f"'bpm' out of plausible range: {self.bpm}")
        if self.camelot and not _valid_camelot(self.camelot):
            errors.append(f"'camelot' is not a valid Camelot code: {self.camelot}")
        return errors

    def to_frontmatter(self) -> dict[str, Any]:
        data = super().to_frontmatter()
        data.update({
            "title": self.title, "artist": self.artist,
            "album": self.album or None, "genre": self.genre or None,
            "year": self.year, "isrc": self.isrc or None,
            "bpm": round(self.bpm, 2) if self.bpm is not None else None,
            "key": self.key or None, "camelot": self.camelot or None,
            "duration": self.duration, "duration_fmt": self.duration_fmt or None,
            "cue_points": self.cue_points, "loops": self.loops,
        })
        return data

    def note_body(self) -> str:
        lines = [f"# {self.title}", "", f"**Artist:** [[{self.artist}]]"]
        if self.album: lines.append(f"**Album:** [[{self.album}]]")
        if self.genre: lines.append(f"**Genre:** [[{self.genre}]]")
        lines.append("")
        if self.bpm or self.camelot:
            parts = []
            if self.bpm: parts.append(f"BPM: **{self.bpm:.1f}**")
            if self.camelot: parts.append(f"Key: **{self.camelot}** ({self.key})")
            if self.duration_fmt: parts.append(f"Duration: **{self.duration_fmt}**")
            lines += [" · ".join(parts), ""]
        if self.cue_points:
            lines.append("### Cue Points")
            for i, t in enumerate(self.cue_points, 1):
                lines.append(f"- Cue {i}: `{t:.2f}s`")
            lines.append("")
        if self.camelot:
            lines += ["### Compatible Tracks", "```dataview",
                       "TABLE artist, bpm, camelot, key", 'FROM "Music"',
                       f'WHERE camelot = "{self.camelot}" AND id != "{self.id}"',
                       "SORT bpm ASC", "```"]
        return "\n".join(lines)

    def vault_path_components(self) -> list[str]:
        parts = [self.genre or "Unknown Genre", self.artist or "Unknown Artist"]
        if self.album: parts.append(self.album)
        return parts
