# Photo Organizer + Obsidian Integration

Automatically sorts photos into a structured folder tree and generates
Obsidian Markdown notes for every image — complete with frontmatter,
embedded image, wikilinks, and hashtags ready for graph view.

---

## What it does

For every photo it:

1. Reads EXIF data (date, GPS coordinates, camera model, aperture, ISO…)
2. Reverse-geocodes GPS → city + country (offline, no API key needed)
3. Runs CLIP (local AI) to detect scenes and objects (beach, sunset, food…)
4. Detects and clusters faces — unknown people get auto-labels you can rename later
5. Moves the photo to `<output>/<year>/<month-name>/<city>/filename.jpg`
6. Writes a `.md` note to your Obsidian vault

---

## Installation

### Prerequisites

```bash
# macOS
brew install cmake

# Ubuntu / Debian
sudo apt-get install cmake build-essential
```

### Python packages

```bash
pip install -r requirements.txt
```

> `face_recognition` needs `dlib` which requires CMake.  
> If you want to skip face detection, use `--skip-faces`.

---

## Usage

```bash
python photo_organizer.py \
    --input  ~/Downloads/photos \
    --output ~/Documents/MyVault/photos \
    --vault  ~/Documents/MyVault \
    [--dry-run]        # preview without moving anything
    [--skip-ai]        # skip CLIP scene tagging
    [--skip-faces]     # skip face detection
```

### Flags

| Flag | Description |
|------|-------------|
| `--input` | Source folder (searched recursively) |
| `--output` | Destination for sorted photos (must be inside `--vault`) |
| `--vault` | Obsidian vault root |
| `--notes` | Where to write `.md` notes (default: `<vault>/photo-notes`) |
| `--dry-run` | Preview only — nothing is moved or written |
| `--skip-ai` | Disable CLIP scene/object tagging |
| `--skip-faces` | Disable face detection |
| `--rename-faces` | Apply renames from `face_labels.json` to existing notes |

---

## Output structure

### Folder layout

```
MyVault/
├── photos/
│   ├── 2024/
│   │   └── 08-August/
│   │       └── Paris/
│   │           └── DSC_4821.jpg
│   └── 2023/
│       └── 12-December/
│           └── Tokyo/
│               └── IMG_0042.jpg
├── photo-notes/
│   ├── DSC_4821.md
│   └── IMG_0042.md
├── face_labels.json          ← rename person_00 → "Alice" here
└── photo_organizer.db        ← SQLite log of all processed photos
```

### Generated note example

```markdown
---
title: "DSC_4821"
date: 2024-08-14
location: "Paris, France"
country: "FR"
tags: [paris, beach, sunset, travel]
people: [person_00, person_01]
camera: "Canon EOS R5"
focal_length: "35mm"
aperture: "f/2.8"
shutter: "1/200s"
iso: 100
latitude: 48.856613
longitude: 2.352222
dimensions: "6000x4000"
---

![[photos/2024/08-August/Paris/DSC_4821.jpg]]

[[Paris]] · [[France]] · [[2024-08]]
[[person_00]] [[person_01]]
#beach #sunset #travel

Canon EOS R5 · f/2.8 · 1/200s · ISO 100
```

---

## Obsidian graph view tips

- Open graph view (`Ctrl/Cmd + G`) — each tag, person, and location becomes a node
- Install **Dataview** plugin to query photos:
  ```dataview
  TABLE date, location, tags
  FROM "photo-notes"
  WHERE contains(tags, "sunset")
  SORT date DESC
  ```
- Install **Map View** plugin to see GPS-tagged photos on a world map

---

## Renaming people

After the first run, open `face_labels.json`:

```json
{
  "person_00": "person_00",
  "person_01": "person_01"
}
```

Change the **values** to real names:

```json
{
  "person_00": "Alice",
  "person_01": "Bob"
}
```

Then run:

```bash
python photo_organizer.py \
    --vault ~/Documents/MyVault \
    --rename-faces
```

All existing notes are updated automatically.

---

## Customising AI tags

Edit `SCENE_LABELS` near the top of `photo_organizer.py` to add your own categories:

```python
SCENE_LABELS = [
    "beach", "mountain", "forest", "city", ...
    "hiking", "skiing", "birthday", "dog",   # ← add yours
]
```

CLIP is zero-shot — no retraining needed, just add labels.

---

## Performance

| Step | Speed (approx.) |
|------|----------------|
| EXIF + geocode | ~0.1s / photo |
| CLIP tagging (CPU) | ~2–5s / photo |
| CLIP tagging (GPU) | ~0.3s / photo |
| Face detection (HOG) | ~1–3s / photo |

For large libraries (1000+ photos), GPU is recommended for CLIP.  
You can also run `--skip-ai` for a fast first pass and add tags later.
