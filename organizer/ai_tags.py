from __future__ import annotations
"""organizer.ai_tags — CLIP-based zero-shot scene/object tagging.

Thread-safety
-------------
The CLIP model is loaded once via ``preload_clip()`` and then shared
across all worker threads.  Each worker must hold the ``clip_lock``
(a ``threading.Lock`` passed down from the pipeline) while calling
``ai_tag()``.  Do NOT call ``ai_tag()`` concurrently without the lock —
PyTorch inference on the same model is not thread-safe.
"""

import threading
from pathlib import Path
from typing import Callable

SCENE_LABELS: list[str] = [
    "beach", "mountain", "forest", "city", "desert", "snow", "lake", "river",
    "sunset", "sunrise", "night", "indoor", "party", "food", "sport", "travel",
    "portrait", "animal", "architecture", "street", "wedding", "concert",
    "nature", "garden", "office", "market",
]

_clip_model     = None
_clip_processor = None
_load_once      = threading.Lock()   # prevents double-loading on startup


def preload_clip(log_fn: Callable[[str], None] = print) -> None:
    """
    Eagerly load the CLIP model into the module-level globals.
    Call this from the main thread BEFORE spawning workers so that
    every thread shares the same already-loaded model.
    """
    global _clip_model, _clip_processor
    with _load_once:
        if _clip_model is not None:
            return
        log_fn("  [AI] Loading CLIP model (first run may download ~600 MB)...")
        from transformers import CLIPProcessor, CLIPModel
        name            = "openai/clip-vit-base-patch32"
        _clip_processor = CLIPProcessor.from_pretrained(name)
        _clip_model     = CLIPModel.from_pretrained(name)
        _clip_model.eval()
        log_fn("  [AI] CLIP model ready.")


def _load_clip():
    """Lazy-load CLIP (used when called outside a parallel context)."""
    global _clip_model, _clip_processor
    if _clip_model is None:
        preload_clip()
    return _clip_model, _clip_processor


def ai_tag(
    path: Path,
    top_k: int = 5,
    threshold: float = 0.18,
    log_fn: Callable[[str], None] = print,
) -> list[str]:
    """
    Return up to top_k scene/object tags whose CLIP probability exceeds threshold.
    Always returns at least one tag (the highest-scoring label).

    Thread-safety: the caller must hold the pipeline's ``clip_lock`` while
    invoking this function.
    """
    try:
        import torch
        from PIL import Image

        model, processor = _load_clip()
        image  = Image.open(path).convert("RGB")
        inputs = processor(
            text=SCENE_LABELS, images=image,
            return_tensors="pt", padding=True,
        )
        with torch.no_grad():
            probs = model(**inputs).logits_per_image.softmax(dim=1)[0]

        tags = [SCENE_LABELS[i] for i, p in enumerate(probs) if p.item() >= threshold]
        if not tags:
            tags = [SCENE_LABELS[probs.argmax().item()]]
        return tags[:top_k]

    except Exception as e:
        log_fn(f"  [AI] Tag error for {path.name}: {e}")
        return []
