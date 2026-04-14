from __future__ import annotations
"""organizer.hashing — low-level file hashing utilities."""

import hashlib
from pathlib import Path


def sha256_of(path: Path) -> str:
    """Return hex SHA-256 of file contents (streams in 64 KB chunks)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def phash_of(path: Path):
    """
    Return an imagehash.ImageHash perceptual hash for an image.
    Requires: imagehash, Pillow.
    """
    import importlib
    imagehash = importlib.import_module("imagehash")
    from PIL import Image
    img = Image.open(path).convert("RGB")
    return imagehash.phash(img)


def pixel_count(path: Path) -> int:
    """Return width × height for resolution comparison. Returns 0 on error."""
    from PIL import Image
    try:
        with Image.open(path) as img:
            return img.width * img.height
    except Exception:
        return 0
