
from __future__ import annotations
from pathlib import Path
from typing import Any, Iterator
from .models.base import BaseEntity
from .repository import NoteRepository, NoteNotFoundError, _parse_frontmatter, _extract_body, _render_note

_OBSIDIAN_CONFIG = {"app.json": "{}", "workspace.json": "{}"}

class VaultManager:
    def __init__(self, vault_root: Path) -> None:
        self._root = vault_root.expanduser().resolve()
        self._repo = NoteRepository(self._root)

    @property
    def root(self) -> Path: return self._root

    def bootstrap(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        obsidian_dir = self._root / ".obsidian"
        obsidian_dir.mkdir(exist_ok=True)
        for name, content in _OBSIDIAN_CONFIG.items():
            cfg = obsidian_dir / name
            if not cfg.exists(): cfg.write_text(content, encoding="utf-8")
        readme = self._root / "README.md"
        if not readme.exists():
            readme.write_text("# Vault\n\nManaged by Obsidian-Python Core Library.\n", encoding="utf-8")

    def create(self, entity: BaseEntity) -> Path: return self._repo.create(entity)
    def update(self, entity: BaseEntity) -> Path: return self._repo.update(entity)
    def upsert(self, entity: BaseEntity) -> Path: return self._repo.upsert(entity)
    def delete(self, entity_type: str, entity_id: str) -> bool: return self._repo.delete(entity_type, entity_id)
    def exists(self, entity_type: str, entity_id: str) -> bool: return self._repo.exists(entity_type, entity_id)
    def get(self, entity_type: str, entity_id: str) -> BaseEntity: return self._repo.get(entity_type, entity_id)
    def get_raw(self, entity_type: str, entity_id: str) -> dict[str, Any]: return self._repo.get_raw(entity_type, entity_id)
    def query(self, entity_type: str, **filters: Any) -> Iterator[dict[str, Any]]: yield from self._repo.query(entity_type, **filters)
    def iter_all(self, entity_type: str) -> Iterator[dict[str, Any]]: yield from self._repo.iter_all(entity_type)
    def count(self, entity_type: str, **filters: Any) -> int: return sum(1 for _ in self.query(entity_type, **filters))

    def patch(self, entity_type: str, entity_id: str, fields: dict[str, Any]) -> None:
        path = self._repo._find_note_by_id(entity_type, entity_id)
        if path is None or not path.exists():
            raise NoteNotFoundError(f"[{entity_type}] id={entity_id} not found")
        content = path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        fm.update(fields)
        path.write_text(_render_note(fm, _extract_body(content)), encoding="utf-8")

    def rebuild_body(self, entity: BaseEntity) -> None:
        path = self._repo._note_path(entity)
        if not path.exists(): raise NoteNotFoundError(f"Note not found: {path}")
        content = path.read_text(encoding="utf-8")
        path.write_text(_render_note(_parse_frontmatter(content), entity.note_body()), encoding="utf-8")

    def stats(self) -> dict[str, int]:
        from .models.base import _ENTITY_REGISTRY
        return {etype: self.count(etype) for etype in _ENTITY_REGISTRY}

    def __repr__(self) -> str: return f"VaultManager(root={self._root})"
