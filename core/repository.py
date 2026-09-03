
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Iterator
import yaml
from .models.base import BaseEntity, get_entity_class
from .utils.slugify import slugify

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)

class NoteNotFoundError(Exception): pass

class NoteRepository:
    def __init__(self, vault_root: Path) -> None:
        self._root = vault_root.resolve()

    def create(self, entity: BaseEntity) -> Path:
        path = self._note_path(entity)
        if path.exists(): raise FileExistsError(f"Note already exists: {path}")
        self._write_note(entity, path); return path

    def update(self, entity: BaseEntity) -> Path:
        path = self._note_path(entity)
        if not path.exists(): raise NoteNotFoundError(f"Note not found: {path}")
        existing = path.read_text(encoding="utf-8")
        body = _extract_body(existing)
        path.write_text(_render_note(entity.to_frontmatter(), body if body.strip() else entity.note_body()), encoding="utf-8")
        return path

    def upsert(self, entity: BaseEntity) -> Path:
        path = self._note_path(entity)
        return self.update(entity) if path.exists() else self.create(entity)

    def delete(self, entity_type: str, entity_id: str) -> bool:
        path = self._find_note_by_id(entity_type, entity_id)
        if path and path.exists(): path.unlink(); return True
        return False

    def exists(self, entity_type: str, entity_id: str) -> bool:
        path = self._find_note_by_id(entity_type, entity_id)
        return path is not None and path.exists()

    def get_raw(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        path = self._find_note_by_id(entity_type, entity_id)
        if path is None or not path.exists():
            raise NoteNotFoundError(f"[{entity_type}] id={entity_id} not found")
        return _parse_frontmatter(path.read_text(encoding="utf-8"))

    def get(self, entity_type: str, entity_id: str) -> BaseEntity:
        data = self.get_raw(entity_type, entity_id)
        cls = get_entity_class(entity_type)
        if cls is None: raise ValueError(f"No entity class registered for type '{entity_type}'")
        return _dict_to_entity(cls, data)

    def iter_all(self, entity_type: str) -> Iterator[dict[str, Any]]:
        subpath = self._subpath_for_type(entity_type)
        if not subpath.exists(): return
        for md_file in sorted(subpath.rglob("*.md")):
            try:
                fm = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
                if fm.get("type") == entity_type: yield fm
            except Exception: pass

    def query(self, entity_type: str, **filters: Any) -> Iterator[dict[str, Any]]:
        for fm in self.iter_all(entity_type):
            if all(fm.get(k) == v for k, v in filters.items()): yield fm

    def _note_path(self, entity: BaseEntity) -> Path:
        base = self._root / entity.VAULT_SUBPATH
        components = entity.vault_path_components()
        folder = base.joinpath(*components) if components else base
        return folder / f"{slugify(entity.id)}.md"

    def _subpath_for_type(self, entity_type: str) -> Path:
        cls = get_entity_class(entity_type)
        if cls is None: return self._root / entity_type
        try: subpath = cls.__dataclass_fields__["VAULT_SUBPATH"].default
        except (AttributeError, KeyError): subpath = entity_type
        return self._root / subpath

    def _find_note_by_id(self, entity_type: str, entity_id: str) -> "Path | None":
        slug = slugify(entity_id)
        subpath = self._subpath_for_type(entity_type)
        if not subpath.exists(): return None
        for candidate in subpath.rglob(f"{slug}.md"):
            fm = _parse_frontmatter(candidate.read_text(encoding="utf-8"))
            if fm.get("id") == entity_id: return candidate
        for md_file in subpath.rglob("*.md"):
            try:
                fm = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
                if fm.get("id") == entity_id and fm.get("type") == entity_type: return md_file
            except Exception: pass
        return None

    def _write_note(self, entity: BaseEntity, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_render_note(entity.to_frontmatter(), entity.note_body()), encoding="utf-8")

def _render_note(frontmatter: dict[str, Any], body: str) -> str:
    clean_fm = {k: v for k, v in frontmatter.items() if v is not None or isinstance(v, list)}
    fm_str = yaml.dump(clean_fm, allow_unicode=True, default_flow_style=False, sort_keys=True)
    return f"---\n{fm_str}---\n\n{body}"

def _parse_frontmatter(content: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(content)
    if not match: return {}
    try: return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError: return {}

def _extract_body(content: str) -> str:
    match = _FRONTMATTER_RE.match(content)
    return content[match.end():] if match else content

def _dict_to_entity(cls, data: dict[str, Any]) -> BaseEntity:
    import dataclasses
    valid_fields = {f.name for f in dataclasses.fields(cls) if f.init}
    return cls(**{k: v for k, v in data.items() if k in valid_fields})
