
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from ..utils.time import now_iso

_ENTITY_REGISTRY: dict[str, type] = {}

def register_entity_type(cls):
    _ENTITY_REGISTRY[cls.ENTITY_TYPE] = cls
    return cls

def get_entity_class(entity_type: str):
    return _ENTITY_REGISTRY.get(entity_type)

class ValidationError(Exception):
    def __init__(self, entity_type: str, errors: list[str]) -> None:
        self.entity_type = entity_type; self.errors = errors
        super().__init__(f"[{entity_type}] Validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

@dataclass
class BaseEntity:
    ENTITY_TYPE: str = field(default="entity", init=False, repr=False)
    VAULT_SUBPATH: str = field(default="", init=False, repr=False)
    id: str = ""
    created: str = field(default_factory=now_iso)
    updated: str = field(default_factory=now_iso)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        errors = self._collect_errors()
        if errors: raise ValidationError(self.ENTITY_TYPE, errors)

    def _collect_errors(self) -> list[str]:
        errors = []
        if not self.id: errors.append("'id' is required and cannot be empty")
        if not self.created: errors.append("'created' is required")
        return errors

    def validate(self):
        errors = self._collect_errors()
        if errors: raise ValidationError(self.ENTITY_TYPE, errors)

    def to_frontmatter(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.ENTITY_TYPE,
                "created": self.created, "updated": self.updated, "tags": self.tags}

    def note_body(self) -> str: return ""
    def vault_path_components(self) -> list[str]: return []
    def touch(self): self.updated = now_iso()
