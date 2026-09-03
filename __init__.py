"""
organizer — photo/video organisation package.

Modules
-------
hashing      sha256_of, phash_of, pixel_count
duplicates   DuplicateResult, check_duplicate, handle_duplicate
metadata     read_exif, read_video_meta, format_duration, _safe,
             reverse_geocode, SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS
ai_tags      ai_tag, SCENE_LABELS
faces        detect_faces, FACE_TOLERANCE
notes        build_obsidian_note, build_video_note, destination_path, is_video
integrity    IntegrityStatus, IntegrityRecord, verify_move, write_integrity_report
database     init_db, log_photo, log_duplicate, log_integrity
maintenance  apply_face_renames, cleanup_orphan_notes
pipeline     process_vault
"""
