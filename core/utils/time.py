
from __future__ import annotations
from datetime import datetime, timezone
from typing import Union

_PARSE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y:%m:%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
]

def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def to_iso(value: Union[str, datetime, None]) -> "str | None":
    if value is None: return None
    if isinstance(value, datetime): return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, str):
        value = value.strip()
        for fmt in _PARSE_FORMATS:
            try: return datetime.strptime(value, fmt).strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError: continue
    return None

def year_from_iso(iso: "str | None") -> "int | None":
    if not iso: return None
    try: return int(iso[:4])
    except (ValueError, TypeError): return None

def month_label_from_iso(iso: "str | None") -> "str | None":
    if not iso: return None
    try: return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%m-%B")
    except ValueError: return None
