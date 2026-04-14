# SIGNATURES.md — Function reference

> Auto-generated reference. One entry per function: line number, signature, one-line description.
> Use Ctrl+F to jump to any function across the codebase.

## File map

| File | Role |
|------|------|
| `photo_organizer.py` | CLI entry point |
| `duplicate_reviewer.py` | Side-by-side duplicate UI |
| `organizer/hashing.py` | File hashing |
| `organizer/duplicates.py` | Duplicate detection |
| `organizer/metadata.py` | EXIF + video metadata + geocoding |
| `organizer/ai_tags.py` | AI scene tagging (CLIP) |
| `organizer/faces.py` | Face detection + clustering |
| `organizer/notes.py` | Obsidian note generation |
| `organizer/integrity.py` | Post-move integrity verification |
| `organizer/database.py` | SQLite logging |
| `organizer/maintenance.py` | Vault housekeeping |
| `organizer/pipeline.py` | Main orchestration loop |
| `photo_organizer_ui.py` | Desktop GUI |

---
## `photo_organizer.py` — CLI entry point

- **L26** `def parse_args() -> argparse.Namespace`
- **L49** `def main() -> None`

---
## `duplicate_reviewer.py` — Side-by-side duplicate UI

- **L56** `def _fmt_size(path: Path) -> str`
- **L68** `def _img_info(path: Path) -> tuple[int, int]`
  > Return (width, height) or (0, 0).
- **L78** `def _load_thumb(path: Path, max_w: int = THUMB_W, max_h: int = THUMB_H)`
  > Return a PIL ImageTk.PhotoImage scaled to fit the thumbnail box.
- **L91** `def load_pairs(db_path: Path) -> list[dict]`
  > Load unreviewed duplicate pairs from the database.
- **L120** `def mark_reviewed(db_path: Path, dup_id: int, final_action: str) -> None`
  > Update the action field after the user makes a decision.
- **L134** `def __init__(self, vault_root: Path, dry_run: bool = False)`
- **L155** `def _build_ui(self)`
- **L233** `def _photo_panel(self, parent: tk.Frame, col: int, role: str) -> dict`
  > Create one photo panel (thumbnail + metadata). Returns handle dict.
- **L280** `def _load_pairs(self)`
- **L288** `def _render_current(self)`
- **L313** `def _render_panel(self, panel: dict, path: Path, role: str)`
- **L329** `def _bg()`
- **L333** `def _paint(thumb)`
- **L363** `def _highlight_better(self, left_p: Path, right_p: Path)`
  > Put a coloured border on the higher-resolution side.
- **L386** `def _current_pair(self) -> dict`
- **L389** `def _delete_file(self, path: Path, label: str)`
  > Move *path* to the reviewed/ trash folder.
- **L408** `def _advance(self, final_action: str)`
- **L415** `def _keep_left(self)`
  > Delete the duplicate (right), keep the original (left).
- **L421** `def _keep_right(self)`
  > Delete the original (left), keep the duplicate (right).
- **L427** `def _keep_both(self)`
  > Do nothing — keep both files.
- **L431** `def _skip(self)`
  > Skip this pair for now (leave action = 'skip' in DB).
- **L438** `def _show_empty(self)`
- **L452** `def _show_done(self)`
- **L472** `def main()`

---
## `organizer/hashing.py` — File hashing

- **L8** `def sha256_of(path: Path) -> str`
  > Return hex SHA-256 of file contents (streams in 64 KB chunks).
- **L17** `def phash_of(path: Path)`
  > Return an imagehash.ImageHash perceptual hash for an image.
- **L29** `def pixel_count(path: Path) -> int`
  > Return width × height for resolution comparison. Returns 0 on error.

---
## `organizer/duplicates.py` — Duplicate detection

- **L16** `def reset_stores() -> None`
  > Clear in-memory duplicate stores (useful for tests).
- **L26** `def __init__(self, is_exact: bool = False, is_perceptual: bool = False, original: Path | None = None, keep_current: bool = False)`
- **L39** `def is_duplicate(self) -> bool`
- **L43** `def check_duplicate(path: Path, skip_phash: bool = False) -> DuplicateResult`
  > Check whether *path* is a duplicate of something already processed.
- **L85** `def handle_duplicate(path: Path, result: DuplicateResult, dup_action: str, dup_dir: Path, dry_run: bool) -> None`
  > Apply the chosen action to a duplicate file.

---
## `organizer/metadata.py` — EXIF + video metadata + geocoding

- **L17** `def _safe(s: str) -> str`
  > Strip characters unsafe for Obsidian note/file names.
- **L26** `def reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None]`
  > Return (city, country_code) for a lat/lon pair using the offline
- **L46** `def _exif_tags()`
- **L54** `def read_exif(path: Path) -> dict`
  > Extract metadata from an image file via Pillow.
- **L115** `def ratio(v) -> float | None`
- **L147** `def dms_to_decimal(dms, ref: str) -> float | None`
- **L186** `def _check_ffprobe() -> bool`
- **L196** `def _ffprobe_json(path: Path) -> dict`
- **L207** `def _parse_iso6709(s: str) -> tuple[float | None, float | None]`
  > Parse ISO 6709 GPS string → (lat, lon) decimal degrees.
- **L225** `def _dms(v: float) -> float`
- **L244** `def _parse_video_date(raw: str) -> datetime | None`
- **L255** `def read_video_meta(path: Path) -> dict`
  > Extract metadata from a video file via ffprobe.
- **L292** `def _gps_from_tags(tag_dict: dict) -> tuple[float | None, float | None]`
- **L338** `def format_duration(seconds: float | None) -> str`
  > Return a human-readable duration string like '1h 23m 45s'.

---
## `organizer/ai_tags.py` — AI scene tagging (CLIP)

- **L17** `def _load_clip()`
- **L29** `def ai_tag(path: Path, top_k: int = 5, threshold: float = 0.18) -> list[str]`
  > Return up to top_k scene/object tags whose CLIP probability exceeds threshold.

---
## `organizer/faces.py` — Face detection + clustering

- **L14** `def reset_face_state() -> None`
  > Clear all face detection state (useful for tests).
- **L23** `def detect_faces(path: Path) -> list[str]`
  > Detect faces in *path* and return a list of person labels.
- **L69** `def get_face_db() -> dict[int, str]`
  > Return a copy of the current face cluster map.

---
## `organizer/notes.py` — Obsidian note generation

- **L9** `def is_video(path: Path) -> bool`
- **L13** `def destination_path(output_root: Path, meta: dict, city: str | None, filename: str) -> Path`
  > Build the destination path:
- **L30** `def build_obsidian_note(photo_rel_path: str, exif: dict, tags: list[str], people: list[str], city: str | None, country: str | None) -> str`
  > Generate Obsidian Markdown for a photo.
- **L120** `def build_video_note(video_rel_path: str, meta: dict, city: str | None, country: str | None) -> str`
  > Generate Obsidian Markdown for a video file.

---
## `organizer/integrity.py` — Post-move integrity verification

- **L30** `def verify_move(src_path: Path, dst_path: Path, src_hash: str) -> IntegrityRecord`
  > Compare *src_hash* against a fresh hash of *dst_path*.
- **L61** `def write_integrity_report(vault_root: Path, records: list[IntegrityRecord], dry_run: bool) -> None`
  > Write ``integrity_report.md`` to vault root.

---
## `organizer/database.py` — SQLite logging

- **L12** `def init_db(db_path: Path) -> sqlite3.Connection`
  > Create (or open) the SQLite database and ensure all tables exist.
- **L52** `def log_photo(conn: sqlite3.Connection, original: str, dest: str, meta: dict, city: str | None, country: str | None, tags: list, people: list) -> None`
  > Insert or replace a processed-file record.
- **L77** `def log_duplicate(conn: sqlite3.Connection, path: str, original: str, kind: str, action: str, kept: bool) -> None`
  > Log a duplicate detection event.
- **L94** `def log_integrity(conn: sqlite3.Connection, record: IntegrityRecord) -> None`
  > Log the result of a post-move integrity check.

---
## `organizer/maintenance.py` — Vault housekeeping

- **L13** `def apply_face_renames(vault_root: Path, notes_dir: Path) -> int`
  > Replace auto-generated ``person_XX`` labels in all notes with human names
- **L87** `def cleanup_orphan_notes(notes_dir: Path, vault_root: Path, dry_run: bool = False) -> tuple[int, int]`
  > Delete ``.md`` notes whose embedded media file no longer exists.

---
## `organizer/pipeline.py` — Main orchestration loop

- **L22** `def _safe_note_path(notes_dir: Path, stem: str) -> Path`
  > Return a non-colliding .md path under notes_dir.
- **L32** `def _safe_dest(dest: Path) -> Path`
  > Return a non-colliding destination path.
- **L42** `def process_vault(input_dir: Path, output_dir: Path, vault_root: Path, notes_dir: Path, dry_run: bool = False, skip_ai: bool = False, skip_faces: bool = False, skip_video: bool = False, dup_action: str = 'skip', dup_report: bool = False, skip_phash: bool = False, integrity_report: bool = True) -> None`
  > Main orchestration loop.
- **L237** `def _write_dup_report(vault_root: Path, dup_log: list[dict], dry_run: bool) -> None`
  > Write ``duplicates_report.md`` to vault root.

---
## `photo_organizer_ui.py` — Desktop GUI

- **L37** `def _pick_dir(var: tk.StringVar, title: str = 'Select folder')`
- **L43** `def _labeled_row(parent, label: str, row: int, col: int = 0, colspan: int = 1, pady: int = 4) -> tk.Label`
- **L52** `def _entry(parent, textvariable, row: int, col: int = 0, colspan: int = 2, width: int = 38) -> tk.Entry`
- **L64** `def _browse_row(parent, var: tk.StringVar, row: int, title: str)`
  > Entry + Browse button on same row.
- **L86** `def _separator(parent, row: int)`
- **L92** `def _section_title(parent, text: str, row: int)`
- **L100** `def _check(parent, text: str, var: tk.BooleanVar, row: int)`
- **L114** `def __init__(self)`
- **L146** `def _configure_style(self)`
- **L163** `def _build_layout(self)`
- **L171** `def _build_sidebar(self)`
- **L199** `def _on_configure(e)`
- **L220** `def _populate_sidebar(self, p)`
- **L392** `def _build_log_panel(self)`
- **L447** `def _log_write(self, text: str, tag: str = 'info')`
- **L453** `def _clear_log(self)`
- **L459** `def _poll_log(self)`
  > Drain the queue and paint new lines — runs on the main thread.
- **L473** `def _build_args(self) -> list[str]`
- **L509** `def _set_running(self, running: bool)`
- **L522** `def _on_stop(self)`
- **L528** `def _on_run(self)`
- **L555** `def _run_process(self, args: list[str])`
- **L610** `def _update_integrity()`
- **L646** `def _on_open_reviewer(self)`
  > Launch the side-by-side duplicate reviewer as a separate window.
- **L668** `def _on_rename_faces(self)`
  > Run --rename-faces via CLI (called after editor saves).
- **L686** `def _open_face_editor(self)`
  > Open an inline editor dialog to rename face labels.
- **L749** `def _save_and_apply()`
- **L758** `def _save_only()`
- **L792** `def _on_cleanup_notes(self)`
  > Run --cleanup-notes (with current dry-run setting).
- **L827** `def _prefs_path(self) -> Path`
- **L830** `def _save_prefs(self)`
- **L851** `def _load_prefs(self)`
- **L872** `def on_close(self)`
