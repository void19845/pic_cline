
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from .base import BaseEntity

@dataclass
class MediaEntity(BaseEntity):
    ENTITY_TYPE: str = field(default="media", init=False, repr=False)
    VAULT_SUBPATH: str = field(default="", init=False, repr=False)
    file_path: str = ""
    file_size: "int | None" = None
    sha256: str = ""
    source_url: str = ""
    date_added: str = ""

    def _collect_errors(self):
        errors = super()._collect_errors()
        if not self.file_path: errors.append("'file_path' is required for media entities")
        return errors

    def to_frontmatter(self) -> dict[str, Any]:
        data = super().to_frontmatter()
        data.update({"file_path": self.file_path, "file_size": self.file_size,
                      "sha256": self.sha256 or None, "source_url": self.source_url or None,
                      "date_added": self.date_added or None})
        return data
