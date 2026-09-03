from __future__ import annotations
"""
organizer.writer — single-threaded vault writer.

Worker threads (organizer.worker.process_one) never call vault.upsert()
themselves. They build an entity and hand it to VaultWriter.submit(),
which queues it for the one dedicated writer thread to persist.

Why: obsidian_core.NoteRepository has no internal locking around
create()/update()/upsert() (check-exists-then-write is not atomic).
Serializing every write through a single thread sidesteps that
question entirely instead of relying on per-entity locks — this is
the same Discovery Queue -> Worker Pool -> Results Queue -> Writer
Thread pattern already used in Document Parser.
"""

import queue
import threading
from dataclasses import dataclass

from core import BaseEntity, VaultManager

_STOP = object()  # sentinel


@dataclass
class WriteError:
    entity_id: str
    entity_type: str
    error: str


class VaultWriter:
    """Owns every vault.upsert() call for one process_vault() run."""

    def __init__(self, vault: VaultManager) -> None:
        self._vault = vault
        self._q: "queue.Queue[object]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = False
        self.errors: list[WriteError] = []
        self.written = 0

    def start(self) -> None:
        if not self._started:
            self._started = True
            self._thread.start()

    def submit(self, entity: BaseEntity) -> None:
        """Queue an entity for writing. Non-blocking; call from any worker thread."""
        if not self._started:
            raise RuntimeError("VaultWriter.submit() called before start()")
        self._q.put(entity)

    def stop_and_join(self, timeout: float | None = None) -> None:
        """Signal the writer to drain the queue and stop. Blocks until done."""
        if not self._started:
            return
        self._q.put(_STOP)
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            job = self._q.get()
            try:
                if job is _STOP:
                    return
                entity: BaseEntity = job  # type: ignore[assignment]
                try:
                    self._vault.upsert(entity)
                    self.written += 1
                except Exception as exc:
                    self.errors.append(WriteError(
                        entity_id=entity.id, entity_type=entity.ENTITY_TYPE,
                        error=str(exc),
                    ))
                    print(f"  [writer] FAILED to write {entity.ENTITY_TYPE} "
                          f"{entity.id}: {exc}")
            finally:
                self._q.task_done()
