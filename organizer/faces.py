from __future__ import annotations
"""organizer.faces — face detection and automatic clustering."""

from pathlib import Path

FACE_TOLERANCE: float = 0.55   # lower = stricter matching

_face_db:         dict[int, str] = {}   # cluster_id → label ("person_01")
_known_encodings: list           = []
_known_ids:       list[int]      = []
_next_id:         int            = 0


def reset_face_state() -> None:
    """Clear all face detection state (useful for tests)."""
    global _next_id
    _face_db.clear()
    _known_encodings.clear()
    _known_ids.clear()
    _next_id = 0


def detect_faces(path: Path) -> list[str]:
    """
    Detect faces in *path* and return a list of person labels.

    Unknown faces are clustered automatically — each new face cluster gets a
    label like ``person_00``, ``person_01``, etc.  Labels can be renamed later
    via ``face_labels.json`` in the vault root.

    Requires: face_recognition (and cmake + dlib).
    """
    global _next_id
    try:
        import face_recognition  # type: ignore

        img       = face_recognition.load_image_file(str(path))
        locations = face_recognition.face_locations(img, model="hog")
        if not locations:
            return []

        encodings = face_recognition.face_encodings(img, locations)
        labels: list[str] = []

        for enc in encodings:
            if _known_encodings:
                distances = face_recognition.face_distance(_known_encodings, enc)
                best_idx  = int(distances.argmin())
                if distances[best_idx] < FACE_TOLERANCE:
                    labels.append(_face_db[_known_ids[best_idx]])
                    continue

            # New cluster
            cid         = _next_id
            _next_id   += 1
            label       = f"person_{cid:02d}"
            _face_db[cid] = label
            _known_encodings.append(enc)
            _known_ids.append(cid)
            labels.append(label)

        return labels

    except Exception as e:
        print(f"  [Face] Error for {path.name}: {e}")
        return []


def get_face_db() -> dict[int, str]:
    """Return a copy of the current face cluster map."""
    return dict(_face_db)
