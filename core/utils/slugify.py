
from __future__ import annotations
import re, unicodedata

def slugify(value: str, separator: str = "_") -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", separator, value)
    return value.strip(separator)

def to_title_case(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()
