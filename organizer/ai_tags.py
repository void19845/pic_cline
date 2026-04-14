from __future__ import annotations
"""organizer.ai_tags — CLIP-based zero-shot scene/object tagging."""

from pathlib import Path

SCENE_LABELS: list[str] = [
    "beach", "mountain", "forest", "city", "desert", "snow", "lake", "river",
    "sunset", "sunrise", "night", "indoor", "party", "food", "sport", "travel",
    "portrait", "animal", "architecture", "street", "wedding", "concert",
    "nature", "garden", "office", "market",
]

_clip_model     = None
_clip_processor = None


def _load_clip():
    global _clip_model, _clip_processor
    if _clip_model is None:
        print("  [AI] Loading CLIP model (first run may download ~600 MB)…")
        from transformers import CLIPProcessor, CLIPModel
        name = "openai/clip-vit-base-patch32"
        _clip_processor = CLIPProcessor.from_pretrained(name)
        _clip_model     = CLIPModel.from_pretrained(name)
        _clip_model.eval()
    return _clip_model, _clip_processor


def ai_tag(path: Path, top_k: int = 5, threshold: float = 0.18) -> list[str]:
    """
    Return up to top_k scene/object tags whose CLIP probability exceeds threshold.
    Always returns at least one tag (the highest-scoring label).
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
        print(f"  [AI] Tag error for {path.name}: {e}")
        return []
