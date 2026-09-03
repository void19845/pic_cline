# Photo Organizer + Obsidian — Project Context

> **Purpose of this document**
> This file provides a complete technical context for an AI assistant (Claude)
> resuming work on this project, as well as human-readable setup and usage
> instructions. It was generated at the end of an iterative development session
> and reflects the current state of the codebase.

---

> ## 🔄 Migration status (read this first)
>
> **Phase 1 — data layer → `obsidian_core` : DONE.**
> **Phase 2 — UI → PyQt6 : DONE.**
>
> Run it: `python photo_organizer_gui.py` (needs `pip install PyQt6`).
>
> This app used to have its own hand-rolled note writer (`organizer/notes.py`)
> and a parallel SQLite database (`organizer/database.py`). Both are gone.
> The app now imports `obsidian_core` (the shared library also used by
> AutoDJ / Document Parser) instead of reinventing note I/O. The UI is now
> PyQt6, running the pipeline **in-process** via QThread + signals — not
> subprocess + stdout parsing.
>
> **Phase 2 — what was built:**
> - `organizer/reporting.py` (new) — `ProgressReporter` Protocol (`log`,
>   `progress`, `finished`) + `ConsoleReporter`. Every `print()` across
>   `organizer/pipeline.py`, `worker.py`, `indexer.py`, `duplicates.py`,
>   `dup_report.py`, `integrity.py`, `ai_tags.py` was replaced with
>   `reporter.log(...)` / a passed-in `log_fn`. `process_vault()` now
>   takes `reporter=` (defaults to `ConsoleReporter()` — the CLI's stdout
>   is byte-for-byte the same as before, verified) and **returns a
>   `RunSummary`**.
> - `ui/` (new package) — the PyQt6 app. `organizer/` and `core/` still
>   import zero Qt; `ui/pipeline_bridge.py` is the *only* file where Qt
>   and the pipeline meet (`QtReporter(QObject)` implements the Reporter
>   shape by emitting signals; `PipelineController` owns the QThread).
>   ```
>   ui/
>     theme.py             QSS stylesheet, palette ported 1:1 from the
>                           old Tkinter UI (#7c6af7 accent etc.)
>     pipeline_bridge.py    QtReporter, PipelineWorker, PipelineController
>     prefs.py              reads/writes the same photo_organizer_ui.prefs.json
>     main_window.py         thin shell, wires tabs <-> controller
>     tabs/run_tab.py         paths, options, Run button, progress bar
>     tabs/logs_tab.py         live log view (signal-fed, no polling)
>     tabs/review_tab.py       duplicate review — rebuilt on dup_report.py
>     tabs/faces_tab.py         face label editor
>     widgets/path_picker.py   reusable folder-picker row
>   ```
> - **Fixed the Review Duplicates bug from Phase 1's notes**: the old tab
>   queried a `duplicates` SQLite table `init_db()` never created — always
>   empty/broken on a fresh vault. `ReviewTab` now reads
>   `dup_report.load_pending()` / writes via `resolve_pair()`, the
>   Markdown system the pipeline already maintains. Verified end-to-end:
>   ran a real duplicate through the actual UI (real `QTest.mouseClick`,
>   not simulated), pending pair appeared correctly, "Delete duplicate
>   file" deleted it from disk and cleared the pending list.
> - Duplicate-pair review is intentionally simpler than the old tab: it
>   lets you delete the losing copy (if still on disk — `dup_action=skip`
>   leaves it in the source folder) or dismiss the pair. It does not
>   "swap" which copy was kept — that would mean undoing an
>   already-written note and a completed file move, a bigger and riskier
>   operation than a review screen should do silently.
> - `phash_threshold` is still `organizer.duplicates.PHASH_THRESHOLD`
>   process-global mutable state (pre-existing design) — `MainWindow`
>   sets it right before starting a run. Noted as debt, not fixed here;
>   fixing it means threading the threshold through `check_duplicate()`
>   instead, which is a `duplicates.py` change, not a UI one.
> - `--dup-report` (CLI flag) was already vestigial — `args.dup_report`
>   is never read by `main()`. Not surfaced in the new UI; not fixed
>   either (out of scope for a UI pass).
>
> **Tested, not just written** — everything below ran for real, not just
> `py_compile`:
> - `QtReporter`/`PipelineController`: 200-entity concurrent-write stress
>   test (Phase 1) plus a full `process_vault()` run through a real
>   `QEventLoop`, cross-thread signals verified (31 log lines, 4/4
>   progress ticks, structured `RunSummary` all correct).
> - Full `MainWindow` instantiated in `QT_QPA_PLATFORM=offscreen` mode
>   (no display needed, real Qt widget construction — this is how the
>   whole UI was verified without ever needing a GUI to look at).
> - End-to-end through the **actual widgets**: `QTest.mouseClick()` on
>   the real Run button, real duplicate produced a real pending pair in
>   Review, real click on Delete removed the file and cleared the list.
> - Faces tab: wrote a `face_labels.json`, edited a name through the
>   real `QLineEdit`, clicked Apply, confirmed the file round-tripped
>   correctly.
> - Prefs: closed the window (`closeEvent`), reopened, confirmed every
>   field reloaded from `photo_organizer_ui.prefs.json` — the same file
>   the old Tkinter UI used, so upgrading doesn't lose anyone's config.
>
> **What did NOT change / is still open:**
> - `photo_organizer_ui.py` (Tkinter) is **still present, untouched**.
>   It's superseded by `photo_organizer_gui.py` but not deleted —
>   validate the new one on real data before removing the old one.
> - `ai_tags.py` (CLIP always-CPU, text embeddings recomputed per image)
>   and `faces.py` are untouched — real optimization targets, orthogonal
>   to both migration phases.
> - No packaging/installer yet (`pip install PyQt6` + `python
>   photo_organizer_gui.py` for now).

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [File Structure](#2-file-structure)
3. [Setup & Installation](#3-setup--installation)
4. [Usage](#4-usage)
5. [Architecture & Module Reference](#5-architecture--module-reference)
6. [Key Design Decisions](#6-key-design-decisions)
7. [Known Bugs & Open Issues](#7-known-bugs--open-issues)
8. [LLM Context — What the AI needs to know](#8-llm-context--what-the-ai-needs-to-know)

---

## 1. Project Overview

A desktop application that:
- **Sorts photos and videos** from a source folder into a structured vault:
  `<year>/<MM-MonthName>/<city>/filename`
- **Tags media** using CLIP (zero-shot scene/object detection) and
  `face_recognition` (automatic face clustering)
- **Extracts metadata** via Pillow EXIF (photos) and ffprobe (videos),
  including GPS reverse-geocoded to city/country
- **Detects duplicates** — exact (SHA-256) and near-duplicate (pHash) —
  comparing against the **entire vault**, not just the current batch
- **Generates Obsidian Markdown notes** per file with frontmatter, wikilinks,
  and embedded media, ready for graph view
- **Verifies file integrity** via SHA-256 comparison after every move
- Provides a **fullscreen Tkinter UI** with live logs, tabbed panels (Logs /
  Review Duplicates / Face Labels), progress bar, and hot-reload i18n
- Supports **4 languages**: English, Français, Español, 日本語
- Processes files in **parallel** using a hybrid ThreadPoolExecutor

---

## 2. File Structure

```
pic_cline/
├── photo_organizer.py          # CLI entry point (~100 lines)
├── photo_organizer_ui.py       # Tkinter desktop GUI (~1700 lines)
├── duplicate_reviewer.py       # Legacy standalone reviewer (superseded by UI tab)
├── requirements.txt
│
├── organizer/                  # Core package
│   ├── __init__.py
│   ├── hashing.py              # sha256_of, phash_of, pixel_count
│   ├── duplicates.py           # DuplicateResult, check_duplicate, seed_from_existing
│   ├── indexer.py              # index_vault — pre-seeds stores before each run
│   ├── metadata.py             # read_exif, read_video_meta, reverse_geocode
│   ├── ai_tags.py              # preload_clip, ai_tag (CLIP zero-shot)
│   ├── faces.py                # detect_faces, get_face_db (dlib HOG)
│   ├── notes.py                # build_obsidian_note, build_video_note, destination_path
│   ├── integrity.py            # IntegrityRecord, verify_move, write_integrity_report
│   ├── database.py             # SQLite: init_db, log_photo, log_integrity
│   ├── dup_report.py           # DupPair, merge_and_save, resolve_pair, load_pending
│   ├── maintenance.py          # apply_face_renames, cleanup_orphan_notes
│   ├── worker.py               # process_one — per-file parallel worker
│   ├── pipeline.py             # process_vault — main orchestration loop
│   └── i18n.py                 # t(), set_language(), detect_language()
│
├── locales/
│   ├── en.json
│   ├── fr.json
│   ├── es.json
│   └── ja.json
│
└── SIGNATURES.md               # Auto-generated function reference (use for quick lookup)
```

### Vault output structure

```
MyVault/
├── photos/
│   └── 2024/
│       └── 08-August/
│           └── Paris/
│               └── DSC_4821.jpg
├── photo-notes/
│   └── DSC_4821.md
├── duplicates/
│   └── reviewed/               # files moved here by the duplicate reviewer
├── face_labels.json            # person_00 -> "Alice" mapping
├── duplicates_report.md        # pending duplicate pairs
├── duplicates_archive.md       # resolved duplicate pairs (append-only)
├── integrity_report.md
└── photo_organizer.db          # SQLite: tables photos + integrity
```

---

## 3. Setup & Installation

### Prerequisites

```bash
# macOS
brew install ffmpeg cmake

# Ubuntu / Debian
sudo apt install ffmpeg cmake build-essential

# Windows
# Install ffmpeg: https://ffmpeg.org/download.html
# Install CMake: https://cmake.org/download/
# Enable Developer Mode for symlink support (optional, for HuggingFace cache)
```

### Python environment

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### requirements.txt (key dependencies)

```
Pillow>=10.0
piexif>=1.1.3
reverse_geocoder>=1.5.1
face_recognition>=1.3.0    # needs cmake + dlib
numpy>=1.24
transformers>=4.35          # CLIP
torch>=2.0
torchvision>=0.15
imagehash>=4.3
tqdm>=4.65
```

---

## 4. Usage

### Desktop GUI (recommended)

```bash
python photo_organizer_ui.py
```

- Fullscreen by default. `F11` or `Esc` to toggle.
- Set source folder, output folder, and vault root in the sidebar.
- **Dry Run** is ON by default — preview without moving anything.
- Language auto-detected from OS; changeable in the sidebar.

### CLI

```bash
# Normal run
python photo_organizer.py \
  --input  ~/Downloads/photos \
  --output ~/vault/media \
  --vault  ~/vault

# Dry run
python photo_organizer.py --input ... --output ... --vault ... --dry-run

# Maintenance commands (no --input / --output needed)
python photo_organizer.py --vault ~/vault --rename-faces
python photo_organizer.py --vault ~/vault --cleanup-notes [--dry-run]
```

### All CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | — | Source media folder |
| `--output` | — | Destination inside vault |
| `--vault` | — | Obsidian vault root (required) |
| `--notes` | `<vault>/photo-notes` | Notes output folder |
| `--dry-run` | off | Preview only |
| `--skip-ai` | off | Disable CLIP tagging |
| `--skip-faces` | off | Disable face detection |
| `--skip-video` | off | Photos only |
| `--dup-action` | `skip` | `skip` / `move` / `trash` |
| `--dup-report` | off | Write duplicates_report.md |
| `--skip-phash` | off | Exact hash only (faster) |
| `--phash-threshold` | `8` | Hamming distance for near-dup |
| `--io-workers` | cpu-1 | I/O thread count |
| `--ai-workers` | cpu/2 | Max concurrent AI inferences |
| `--no-integrity-report` | off | Disable integrity_report.md |
| `--rename-faces` | — | Apply face_labels.json to notes |
| `--cleanup-notes` | — | Delete orphan .md notes |

---

## 5. Architecture & Module Reference

### Concurrency model

```
Main thread (sequential)
  scan input_dir
  index_vault()          <- pre-seeds duplicate stores with existing vault files
  reset_stores()         <- always start fresh
  preload_clip()         <- loads CLIP once before workers start
  for each file:
    check_duplicate()    <- sequential, not thread-safe
    pool.submit(process_one, ...)

ThreadPoolExecutor (io_workers threads)
  process_one():
    read_exif / read_video_meta
    reverse_geocode
    ai_tag()      <- acquires _SemLock(ai_sem, clip_lock)
    detect_faces  <- acquires _SemLock(ai_sem, face_lock)
    sha256_of
    shutil.move
    verify_move
    write .md note
    log to SQLite

as_completed() <- collect results in completion order
merge_and_save()  <- write/merge duplicates_report.md
write_integrity_report()
```

### Duplicate detection flow

```
1. index_vault()
   for every media file already in vault:
     seed_from_existing(path)  -> registers in _exact_hashes + _phash_store
                                   WITHOUT creating a DuplicateResult

2. For each incoming file:
   check_duplicate(path)
     -> SHA-256 match?  -> DuplicateResult(is_exact=True, ...)
     -> pHash distance <= PHASH_THRESHOLD?  -> DuplicateResult(is_perceptual=True, ...)
     -> Not a duplicate -> registers path in stores, returns empty DuplicateResult

3. If duplicate:
   build_dup_pair() -> DupPair(sha_original, sha_duplicate, path_original, ...)
   merge_and_save(vault_root, new_pairs)  -> writes/merges duplicates_report.md

4. UI Review tab:
   load_pending(vault_root) -> reads pending DupPairs from duplicates_report.md
   resolve_pair(vault_root, key, status) -> moves pair to duplicates_archive.md
```

### Duplicate pair identity key

```
key = f"{sha_original}:{sha_duplicate}:{path_original}"
```
Robust against renames, survives re-runs, never collides even with near-identical
hash pairs from different sources.

---

### Module signatures

#### `organizer/hashing.py` — File hashing utilities

```python
def sha256_of(path: Path) -> str
    # Return hex SHA-256 of file contents (streams in 64 KB chunks)

def phash_of(path: Path)
    # Return imagehash.ImageHash perceptual hash for an image
    # Requires: imagehash, Pillow

def pixel_count(path: Path) -> int
    # Return width x height for resolution comparison. Returns 0 on error.
```

#### `organizer/duplicates.py` — Duplicate detection + stores

```python
PHASH_THRESHOLD: int = 8   # module-level, set by pipeline from --phash-threshold

def reset_stores() -> None
    # Clear in-memory duplicate stores (called at start of every run)

def seed_from_existing(path: Path, skip_phash: bool = False) -> None
    # Register an existing vault file WITHOUT declaring it a duplicate.
    # Used by index_vault() to pre-populate stores before the run.

def check_duplicate(path: Path, skip_phash: bool = False) -> DuplicateResult
    # Check whether path is a duplicate of something already in stores.
    # Returns DuplicateResult with .is_duplicate, .sha_current, .sha_original,
    # .phash_distance, .original (Path), .keep_current (bool)

def handle_duplicate(path: Path, result: DuplicateResult,
                     dup_action: str, dup_dir: Path, dry_run: bool) -> None
    # Apply skip/move/trash action to a duplicate file
```

#### `organizer/indexer.py` — Vault pre-indexer

```python
_SKIP_DIRS = frozenset({"duplicates", "photo-notes", ".obsidian", ".git", ".trash"})

def index_vault(vault_root: Path, skip_phash: bool = False,
                skip_video: bool = False, input_dir: Path | None = None) -> int
    # Pre-seed duplicate stores with every media file already in the vault.
    # Excludes: _SKIP_DIRS, input_dir (the incoming batch).
    # Returns count of indexed files.
    # Prints heartbeat every 100 files.
```

#### `organizer/metadata.py` — EXIF + video metadata + geocoding

```python
SUPPORTED_EXTENSIONS: set[str]  # photo extensions
VIDEO_EXTENSIONS: set[str]       # .mp4 .mov .m4v

def reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None]
    # Returns (city, country_code) using offline reverse_geocoder

def read_exif(path: Path) -> dict
    # Keys: date, lat, lon, camera_make, camera_model,
    #       focal_length, aperture, shutter, iso, width, height
    # Uses Pillow getexif() with fallback to _getexif()
    # GPS: reads from IFD tag 34853, validates -90<=lat<=90, -180<=lon<=180

def read_video_meta(path: Path) -> dict
    # Keys: date, lat, lon, duration_s, width, height, codec,
    #       camera_make, camera_model
    # Uses ffprobe JSON output. GPS: searches format tags then stream tags.
    # Date fallback chain: Apple QuickTime tag -> creation_time -> file mtime

def format_duration(seconds: float | None) -> str
    # Returns "1h 23m 45s" style string

def _parse_iso6709(s: str) -> tuple[float | None, float | None]
    # Handles decimal (+48.856+2.352/) and DMS compact (+482838+0021112/) variants
    # 3rd altitude component is silently ignored
```

#### `organizer/ai_tags.py` — CLIP scene tagging

```python
SCENE_LABELS: list[str]  # 26 labels: beach, mountain, city, sunset, ...
                          # Add custom labels here — no retraining needed

def preload_clip() -> None
    # Eagerly load CLIP model BEFORE spawning workers.
    # Must be called from main thread. Protected by threading.Lock.
    # Downloads ~600 MB on first run, cached in HuggingFace cache.

def ai_tag(path: Path, top_k: int = 5, threshold: float = 0.18) -> list[str]
    # Returns up to top_k labels with probability >= threshold.
    # Always returns at least 1 label (highest scorer).
    # Caller must hold clip_lock while calling this.
```

#### `organizer/faces.py` — Face detection + clustering

```python
FACE_TOLERANCE: float = 0.55  # lower = stricter matching

def detect_faces(path: Path) -> list[str]
    # Detect faces, return list of labels like ["person_00", "person_01"]
    # New faces get auto-labeled. Caller must hold face_lock.

def get_face_db() -> dict[int, str]
    # Returns copy of current cluster map {cluster_id: label}

def reset_face_state() -> None
    # Clear all face detection state
```

#### `organizer/notes.py` — Obsidian note generation

```python
def destination_path(output_root: Path, meta: dict,
                     city: str | None, filename: str) -> Path
    # Returns: output_root/<year>/<MM-MonthName>/<city|no_location>/filename

def build_obsidian_note(photo_rel_path: str, exif: dict, tags: list[str],
                         people: list[str], city: str | None,
                         country: str | None) -> str
    # Generates YAML frontmatter + wikilinks body for a photo

def build_video_note(video_rel_path: str, meta: dict,
                      city: str | None, country: str | None) -> str
    # Same for video, adds duration/resolution/codec fields

def is_video(path: Path) -> bool
```

#### `organizer/integrity.py` — Post-move SHA-256 verification

```python
class IntegrityStatus(str, Enum):
    OK | MISSING | CORRUPTED | SKIPPED

@dataclass
class IntegrityRecord:
    source, destination, source_hash, dest_hash, status, size_src, size_dst

def verify_move(src_path: Path, dst_path: Path, src_hash: str) -> IntegrityRecord
    # Hash dst_path after move, compare to src_hash.
    # OK if hashes match, MISSING if dst doesn't exist, CORRUPTED if mismatch.

def write_integrity_report(vault_root: Path, records: list[IntegrityRecord],
                             dry_run: bool) -> None
    # Writes integrity_report.md with summary table + problem list
```

#### `organizer/database.py` — SQLite logging

```python
# Tables: photos, integrity  (duplicates table was removed — now in .md)

def init_db(db_path: Path) -> sqlite3.Connection
    # Creates tables, DROPs legacy duplicates table if present

def log_photo(conn, original, dest, meta, city, country, tags, people) -> None
def log_integrity(conn, record: IntegrityRecord) -> None
```

#### `organizer/dup_report.py` — Markdown duplicate report

```python
REPORT_FILE  = "duplicates_report.md"    # pending pairs
ARCHIVE_FILE = "duplicates_archive.md"  # resolved pairs (append-only)

@dataclass
class DupPair:
    # Fields: sha_original, sha_duplicate, path_original, path_duplicate,
    #         kind, phash_distance, res_original, res_duplicate,
    #         size_original, size_duplicate, detected_at,
    #         vault_original, vault_duplicate, status
    def key(self) -> str  # composite key for deduplication

def build_dup_pair(original_path, duplicate_path, sha_original, sha_duplicate,
                   kind, phash_distance, vault_root) -> DupPair

def merge_and_save(vault_root: Path, new_pairs: list[DupPair],
                   dry_run: bool = False) -> None
    # Merge algorithm:
    #   existing = load pending from duplicates_report.md (keyed by pair.key)
    #   for new_pair: if key exists -> update mutable fields, keep status
    #                 if key is new -> add with status=pending
    #   write merged pending list back to file

def resolve_pair(vault_root: Path, key: str, status: str,
                 dry_run: bool = False) -> bool
    # Remove pair from report, append to archive with new status

def load_pending(vault_root: Path) -> list[DupPair]
    # Read pending pairs for the UI reviewer
```

#### `organizer/maintenance.py` — Vault housekeeping

```python
def apply_face_renames(vault_root: Path, notes_dir: Path) -> int
    # Read face_labels.json, apply renames to all .md notes.
    # Only applies entries where value != key.
    # Uses regex to target [[person_00]] wikilinks and YAML list positions.
    # Returns count of notes updated.

def cleanup_orphan_notes(notes_dir: Path, vault_root: Path,
                          dry_run: bool = False) -> tuple[int, int]
    # Parse ![[...]] embeds from each .md note.
    # If ALL embeds point to missing files -> delete note (or preview).
    # If SOME embeds missing -> warn but keep note.
    # Returns (orphans_found, orphans_deleted)
```

#### `organizer/worker.py` — Per-file parallel worker

```python
# Module-level locks: _io_lock, _db_lock, _log_lock

def _safe_dest(dest: Path) -> Path
    # Atomically reserves a non-colliding filename by creating an empty
    # placeholder file under _io_lock. Race-condition-safe.

def process_one(item, output_dir, vault_root, notes_dir, dry_run,
                skip_ai, skip_faces, clip_lock, face_lock,
                db_conn, log_db) -> WorkerResult
    # Full pipeline for one file:
    # metadata -> geocode -> CLIP (with clip_lock) -> faces (with face_lock)
    # -> destination_path -> sha256_of -> shutil.move -> verify_move
    # -> build note -> write note -> log_photo
    #
    # If output_dir is outside vault_root: falls back to filename-only embed path
    # Errors are caught, logged with last 3 traceback lines, result.success=False
```

#### `organizer/pipeline.py` — Main orchestration loop

```python
def process_vault(
    input_dir, output_dir, vault_root, notes_dir,
    dry_run=False, skip_ai=False, skip_faces=False, skip_video=False,
    dup_action='skip', skip_phash=False, integrity_report=True,
    io_workers=None, ai_workers=None
) -> None
    # Order of operations:
    # 1. Resolve + validate paths (warn if output_dir outside vault_root)
    # 2. reset_stores()
    # 3. index_vault(vault_root, skip_phash, skip_video, input_dir)
    # 4. preload_clip() (if not skip_ai)
    # 5. Sequential: check_duplicate() -> skip OR pool.submit(process_one)
    # 6. as_completed() -> collect WorkerResult, log_integrity
    # 7. merge face_labels.json
    # 8. merge_and_save(vault_root, new_dup_pairs)
    # 9. write_integrity_report()

# _SemLock inner class:
#   Combines Semaphore(n_ai) + Lock for AI sections.
#   Semaphore limits concurrent AI jobs; Lock ensures single model use.
```

#### `organizer/i18n.py` — Internationalisation

```python
# Locale files: locales/{en,fr,es,ja}.json
# Each file has "_meta": {"lang": "...", "code": "..."} + 63 translation keys

def detect_language() -> str
    # Checks: LANG/LANGUAGE env vars -> locale.getdefaultlocale() -> winreg (Windows)
    # Returns closest supported code, fallback 'en'

def set_language(code: str) -> None
    # Loads JSON, merges with English fallback, fires all on_language_change callbacks

def t(key: str, **kwargs) -> str
    # Translate key. Supports str.format() placeholders: t("faces_count", n=5)
    # Returns key itself if not found.

def on_language_change(callback: Callable[[str], None]) -> None
    # Register callback for hot-reload. UI registers _retranslate() here.

def available_languages() -> list[dict]
    # Returns [{"code": "en", "lang": "English"}, ...]
```

#### `photo_organizer_ui.py` — Desktop GUI

```python
# Key UI patterns:

# i18n registration
self._reg(widget, attr, key)          # register widget for retranslation
self._retranslate(code)               # updates all _i18n_widgets on language change

# Progress bar
self._set_progress_indeterminate("progress_loading")   # spinner mode
self._set_progress_determinate(current, total)          # % mode
self._finish_progress()                                  # 100% green

# Tab switching
self._switch_tab("logs" | "review" | "faces")

# Duplicate reviewer
_SemLock: combines threading.Semaphore + Lock for AI concurrency limiting
_dup_history: list of dicts for undo support
  {"idx", "action", "pair_id", "deleted_src", "deleted_dst"}

# Python resolver
PYTHON = _find_python()   # finds interpreter: sys.executable -> venv -> PATH
# Used in all subprocess.Popen calls instead of sys.executable
```

---

## 6. Key Design Decisions

### Why Markdown for duplicate storage (not SQLite)?

The `duplicates` table was removed from SQLite. Duplicate pairs now live in
`duplicates_report.md` (pending) and `duplicates_archive.md` (resolved).

**Reasons:**
- Readable and editable directly in Obsidian
- Merge-friendly: each run updates only changed pairs without full rewrite
- The composite key `sha_original:sha_duplicate:path_original` survives renames
  and re-runs without needing a DB schema
- Resolved pairs move to the archive (append-only) — audit trail without bloat

### Why ThreadPoolExecutor instead of ProcessPool for CLIP?

CLIP lives in one process and is shared via `threading.Lock`. ProcessPool
would require pickling the model (not supported by PyTorch) or IPC.
The GIL is released during PyTorch C++ inference and all I/O, so threads
give real parallelism for our workload.

### Why `_safe_dest` creates a placeholder file?

Without a placeholder, two threads could both check `final.exists()`,
both get `False`, both proceed with the same path, and one would overwrite
the other. Creating an empty file atomically under `_io_lock` reserves the
slot before `shutil.move` runs outside the lock.

### Why pre-index the entire vault before each run?

Without pre-indexing, `check_duplicate` only compares incoming files against
each other — photos already sorted on a previous run were never checked.
`index_vault()` calls `seed_from_existing()` which populates `_exact_hashes`
and `_phash_store` without creating DuplicateResult objects.
`input_dir` is explicitly excluded so incoming files don't register themselves.

### Why `from __future__ import annotations` everywhere?

Enables `dict[str, Path]`, `list[tuple]`, `str | None` on Python 3.8/3.9
without importing from `typing`. All type hints become lazy strings.

### GPS handling strategy

**Photos (EXIF):** Read from IFD tag 34853 directly (more robust than the
`GPSInfo` dict for HEIC). `ratio()` handles IFDRational, tuples, int, float.
Coordinates are range-validated (-90≤lat≤90, -180≤lon≤180).

**Videos (ffprobe):** ISO 6709 parser handles decimal, DMS-compact, and
3-component (with altitude) variants. GPS searched in format tags first,
then in each stream's tags (GoPro/DJI store GPS in stream tags).

### Unicode on Windows

Windows terminals use cp1252 which cannot encode `→`, `✓`, etc.
Fix applied at two levels:
1. `sys.stdout.reconfigure(encoding="utf-8")` at CLI startup
2. `PYTHONIOENCODING=utf-8` in subprocess env from UI
3. All Unicode symbols replaced with ASCII: `->`, `[OK]`, `[!!]`

---

## 7. Known Bugs & Open Issues

### Active issues

| # | Severity | Description | Location |
|---|----------|-------------|----------|
| 1 | Medium | `output_dir` outside `vault_root` produces a `ValueError` in `dest.relative_to(vault_root)` — now caught with a warning and filename-only fallback, but Obsidian graph links won't work correctly | `worker.py` L~170 |
| 2 | Low | `_safe_dest` creates an empty placeholder file; if `shutil.move` fails after the placeholder is created, a stale empty file remains at the destination | `worker.py:_safe_dest` |
| 3 | Low | The `duplicate_reviewer.py` standalone file uses the old SQLite-based `load_pairs()` which queries the now-removed `duplicates` table — it will fail if run directly | `duplicate_reviewer.py` |
| 4 | Low | `apply_face_renames` regex may match person labels that appear in filenames or paths, not just in wikilinks | `maintenance.py:apply_face_renames` |
| 5 | Low | If CLIP model download fails mid-way (network interruption), the model is partially cached and subsequent runs may fail with a cryptic HuggingFace error | `ai_tags.py:preload_clip` |

### Limitations

- Face recognition requires `cmake` + `dlib` which is complex to install on
  Windows. `--skip-faces` is the recommended workaround until packaging improves.
- `reverse_geocoder` is an offline library with ~4 MB of city data — city names
  may be inaccurate for small towns or rural areas.
- pHash is computed only for images (not videos) — near-duplicate video detection
  uses exact SHA-256 only.
- The i18n system does not retranslate text inside the log output (only UI labels).
- Progress bar total is parsed from `"Found N photo(s) and M video(s)"` — if this
  line doesn't appear (e.g. maintenance commands), the bar stays indeterminate.

---

## 8. LLM Context — What the AI needs to know

### Coding conventions

- **All modules** start with `from __future__ import annotations`
- **Public functions** have a one-line docstring minimum
- **Print statements** use ASCII-only characters (no `→`, `✓`, etc.)
- **Locks** are always passed as parameters, never created inside workers
- **Error handling** in workers: catch `Exception`, print last 3 traceback lines,
  set `result.success = False`, never re-raise
- **i18n**: all visible UI strings go through `t("key")` — never hardcode strings
  in widget constructors. Register widgets with `self._reg(widget, attr, key)`.

### How to add a new feature

1. If it's a new processing step → add it to `worker.py:process_one` and
   return the result in `WorkerResult`
2. If it's a new maintenance command → add it to `maintenance.py`, wire CLI
   flag in `photo_organizer.py`, add UI button in `photo_organizer_ui.py`
3. If it adds new text → add the key to all 4 locale files (`en/fr/es/ja.json`)
4. Update `SIGNATURES.md` by running the extraction script in this document

### How to add a new language

1. Create `locales/<code>.json` by copying `en.json`
2. Translate all values (keep keys in English)
3. Set `"_meta": {"lang": "YourLanguage", "code": "<code>"}`
4. No code changes needed — `available_languages()` picks it up automatically

### Files that must stay in sync

| Change | Files to update |
|--------|----------------|
| New CLI flag | `photo_organizer.py` + `photo_organizer_ui.py` (_build_args) + prefs save/load |
| New UI string | All 4 locale JSON files |
| New DB table | `database.py:init_db` |
| New DupPair field | `dup_report.py`: DupPair dataclass + _COLUMNS + _row + _parse_row |
| New WorkerResult field | `worker.py:WorkerResult` + `pipeline.py` (collect results) |

### Current state summary

The project is **feature-complete for its core scope** with these subsystems
all working:
- [x] Parallel processing (hybrid thread pool)
- [x] Full-vault duplicate detection (pre-indexing)
- [x] EXIF/video metadata + GPS
- [x] CLIP zero-shot tagging
- [x] Face detection + clustering + renaming
- [x] Obsidian note generation with wikilinks
- [x] SHA-256 integrity verification
- [x] Duplicate pair storage in Markdown (report + archive)
- [x] Fullscreen Tkinter UI with 3 tabs
- [x] Progress bar (indeterminate for CLIP load, determinate for file processing)
- [x] Hot-reload i18n (en/fr/es/ja)
- [x] Dry-run mode throughout
- [x] Undo in duplicate reviewer
- [x] Orphan note cleanup
- [x] Windows cp1252 Unicode fix

**Recommended next steps** (not yet implemented):
- Fix `duplicate_reviewer.py` to use `dup_report.load_pending()` instead of SQLite
- Add a `--watch` mode to monitor a folder and process new arrivals automatically
- Add Dataview-compatible frontmatter fields for Obsidian query support
- GPU auto-detection for CLIP (currently always CPU unless torch.cuda is available)
- Packaging as a standalone executable (PyInstaller / cx_Freeze)
