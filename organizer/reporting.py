from __future__ import annotations
"""
organizer.reporting — progress reporting abstraction.

organizer/ never imports Qt (enforced: this package has zero PyQt
dependency, checked by a grep in the test suite -- see
tests/test_no_qt_in_organizer.py). The pipeline reports progress through
this Protocol instead of calling print() directly.

- CLI          -> ConsoleReporter (byte-identical to the pre-Phase-2 stdout)
- PyQt6 UI     -> ui/pipeline_bridge.py:QtReporter, which emits Qt signals
                  instead. That file is the ONLY place PyQt and organizer/
                  meet.

ProgressReporter is a typing.Protocol (structural typing) rather than an
ABC on purpose: QtReporter also inherits QObject, and mixing a real base
class here would fight PyQt's metaclass. Protocol needs no inheritance --
any object with the right methods satisfies it.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class RunSummary:
    """Structured end-of-run result -- what the old code printed as loose
    text lines ('Vault: 4 note(s) written', 'Integrity: 4 OK ...') is now
    also available as data, so a UI can show a completion state without
    parsing text."""
    photos_found:         int = 0
    videos_found:         int = 0
    notes_written:        int = 0
    write_errors:         int = 0
    duplicates_found:     int = 0
    duplicates_actioned:  int = 0
    integrity_ok:         int = 0
    integrity_missing:    int = 0
    integrity_corrupted:  int = 0
    dup_report_path:      Path | None = None
    integrity_report_path: Path | None = None
    dry_run:              bool = False

    @property
    def has_problems(self) -> bool:
        return self.integrity_missing > 0 or self.integrity_corrupted > 0 or self.write_errors > 0


class ProgressReporter(Protocol):
    """Structural type. Three methods -- deliberately minimal:

    log()      -- every human-readable line (what used to be print()).
                  A UI's Logs tab just appends these; nothing to parse.
    progress() -- called once per media item that finishes processing --
                  either a duplicate resolved synchronously in the dedup
                  loop, or a worker future completing (success or error).
                  Deliberately NOT called at dispatch time: with a
                  ThreadPoolExecutor, submission races far ahead of
                  completion, so a bar tied to dispatch count would jump
                  to 100% almost immediately and then sit frozen while
                  the actual (slow) per-file work finishes in the
                  background -- misleading the UI far more than the
                  '[3/12]' log-scraping this Protocol replaced.
    finished() -- called once, at the very end, with structured counts.
    """

    def log(self, message: str) -> None: ...
    def progress(self, current: int, total: int) -> None: ...
    def finished(self, summary: RunSummary) -> None: ...


class ConsoleReporter:
    """Default reporter. log() is a straight print() -- CLI stdout is
    unchanged from before the reporter existed."""

    def log(self, message: str) -> None:
        print(message)

    def progress(self, current: int, total: int) -> None:
        pass  # the per-item log() line already carries this; avoid noise

    def finished(self, summary: RunSummary) -> None:
        pass  # pipeline.py already logs its own summary lines via log()