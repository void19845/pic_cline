from __future__ import annotations
"""
ui.prefs — settings persistence.

Reads/writes the same photo_organizer_ui.prefs.json file the Tkinter UI
used, so upgrading doesn't lose anyone's configured paths. `notes` is
read but ignored (obsidian_core fixes the notes location — see
organizer/pipeline.py) and never written back.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

PREFS_PATH = Path(__file__).resolve().parent.parent / "photo_organizer_ui.prefs.json"


@dataclass
class Prefs:
    input:        str  = ""
    output:        str  = ""
    vault:         str  = ""
    dry_run:       bool = True
    skip_ai:       bool = False
    skip_faces:    bool = False
    skip_video:    bool = False
    skip_phash:    bool = False
    dup_report:    bool = True
    dup_action:    str  = "skip"
    threshold:     int  = 8
    no_integrity:  bool = False
    io_workers:    int  = 0   # 0 = auto
    ai_workers:    int  = 0   # 0 = auto
    language:      str  = ""  # "" = auto-detect

    @classmethod
    def load(cls) -> "Prefs":
        if not PREFS_PATH.exists():
            return cls()
        try:
            data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        try:
            PREFS_PATH.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass   # prefs are a convenience, never block the app on a write failure
