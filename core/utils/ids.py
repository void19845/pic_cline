
from __future__ import annotations
import hashlib, uuid
from pathlib import Path
from .time import now_iso
from .slugify import slugify

def generate_id(entity_type: str, *components: str) -> str:
    raw = ":".join(str(c) for c in components)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"{entity_type}_{digest}"

def generate_id_from_path(entity_type: str, path: Path) -> str:
    return generate_id(entity_type, str(path.resolve()))

def generate_uuid_id(entity_type: str) -> str:
    return f"{entity_type}_{uuid.uuid4().hex[:8]}"

def generate_timestamped_id(entity_type: str, label: str = "") -> str:
    ts = now_iso().replace("-","").replace("T","_").replace(":","")
    parts = [entity_type, ts]
    if label: parts.append(slugify(label)[:32])
    return "_".join(parts)
