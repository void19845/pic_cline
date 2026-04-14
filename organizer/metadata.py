from __future__ import annotations
"""organizer.metadata — EXIF (photos) and ffprobe (videos) metadata extraction."""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

SUPPORTED_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tiff", ".tif", ".webp", ".bmp",
}
VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".m4v"}


def _safe(s: str) -> str:
    """Strip characters unsafe for Obsidian note/file names."""
    return re.sub(r'[\\/:*?"<>|]', "_", s)


# ── Reverse geocoding ────────────────────────────────────────────────────────

_rg = None  # reverse_geocoder module, loaded once

def reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None]:
    """
    Return (city, country_code) for a lat/lon pair using the offline
    reverse_geocoder library.
    """
    global _rg
    if _rg is None:
        import importlib
        _rg = importlib.import_module("reverse_geocoder")
    results = _rg.search([(lat, lon)], verbose=0)
    if results:
        r = results[0]
        return r.get("name"), r.get("cc")
    return None, None


# ── EXIF (photos) ────────────────────────────────────────────────────────────

_EXIF_TAGS = None

def _exif_tags():
    global _EXIF_TAGS
    if _EXIF_TAGS is None:
        from PIL.ExifTags import TAGS, GPSTAGS
        _EXIF_TAGS = (TAGS, GPSTAGS)
    return _EXIF_TAGS


def read_exif(path: Path) -> dict:
    """
    Extract metadata from an image file via Pillow.

    Returns
    -------
    dict with keys:
      date          datetime | None
      lat           float | None
      lon           float | None
      camera_make   str | None
      camera_model  str | None
      focal_length  float | None
      aperture      float | None
      shutter       str | None  (e.g. "1/250s")
      iso           int | None
      width         int | None
      height        int | None
    """
    from PIL import Image

    result: dict = {
        "date": None, "lat": None, "lon": None,
        "camera_make": None, "camera_model": None,
        "focal_length": None, "aperture": None,
        "shutter": None, "iso": None,
        "width": None, "height": None,
    }

    try:
        img = Image.open(path)
        result["width"], result["height"] = img.size

        # getexif() (Pillow ≥9) works for HEIC/JPEG/PNG; fall back to _getexif()
        try:
            exif_data = img.getexif()
            raw = dict(exif_data) if exif_data else None
        except AttributeError:
            raw = img._getexif()

        if not raw:
            return result

        TAGS, GPSTAGS = _exif_tags()
        data = {TAGS.get(k, k): v for k, v in raw.items()}

        # Date
        for field in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
            if field in data:
                try:
                    result["date"] = datetime.strptime(
                        str(data[field])[:19], "%Y:%m:%d %H:%M:%S")
                    break
                except ValueError:
                    pass

        # Camera
        result["camera_make"]  = str(data.get("Make",  "")).strip() or None
        result["camera_model"] = str(data.get("Model", "")).strip() or None

        # Exposure
        def ratio(v) -> float | None:
            if v is None:
                return None
            if hasattr(v, "numerator") and hasattr(v, "denominator"):
                return float(v.numerator) / float(v.denominator) if v.denominator else None
            if isinstance(v, (tuple, list)) and len(v) == 2:
                num, den = v
                return float(num) / float(den) if den else None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        result["focal_length"] = ratio(data.get("FocalLength"))
        result["aperture"]     = ratio(data.get("FNumber"))
        result["iso"]          = data.get("ISOSpeedRatings")

        s = ratio(data.get("ExposureTime"))
        if s and s > 0:
            result["shutter"] = f"1/{round(1/s)}s" if s < 1 else f"{s}s"

        # GPS — read directly from IFD tag 34853 for maximum compatibility
        GPS_IFD_TAG = 34853
        gps_ifd = None
        if GPS_IFD_TAG in raw:
            raw_gps = raw[GPS_IFD_TAG]
            if isinstance(raw_gps, dict):
                gps_ifd = {GPSTAGS.get(k, k): v for k, v in raw_gps.items()}
        if not gps_ifd and isinstance(data.get("GPSInfo"), dict):
            gps_ifd = {GPSTAGS.get(k, k): v for k, v in data["GPSInfo"].items()}

        if gps_ifd:
            def dms_to_decimal(dms, ref: str) -> float | None:
                try:
                    d = ratio(dms[0])
                    m = ratio(dms[1])
                    s = ratio(dms[2])
                    if None in (d, m, s):
                        return None
                    dec = d + m / 60.0 + s / 3600.0
                    return -dec if ref.upper() in ("S", "W") else dec
                except Exception:
                    return None

            lat = dms_to_decimal(
                gps_ifd.get("GPSLatitude"),
                gps_ifd.get("GPSLatitudeRef", "N"),
            )
            lon = dms_to_decimal(
                gps_ifd.get("GPSLongitude"),
                gps_ifd.get("GPSLongitudeRef", "E"),
            )
            if lat is not None and lon is not None:
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    result["lat"] = lat
                    result["lon"] = lon
                else:
                    print(f"  [EXIF] GPS out of range for {path.name}: "
                          f"lat={lat:.4f} lon={lon:.4f}")

    except Exception as e:
        print(f"  [EXIF] Warning for {path.name}: {e}")

    return result


# ── Video metadata (ffprobe) ─────────────────────────────────────────────────

_FFPROBE_OK: bool | None = None


def _check_ffprobe() -> bool:
    try:
        subprocess.run(["ffprobe", "-version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _ffprobe_json(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _parse_iso6709(s: str) -> tuple[float | None, float | None]:
    """
    Parse ISO 6709 GPS string → (lat, lon) decimal degrees.

    Handles
    -------
    +48.8566+002.3522/          decimal degrees (2 components)
    +48.8566+002.3522+35.000/   with altitude   (3rd component ignored)
    +482838+0021112/            DMS compact
    """
    s = s.strip().rstrip("/")
    parts = re.findall(r'[+-][0-9]+(?:\.[0-9]+)?', s)
    if len(parts) < 2:
        return None, None
    try:
        lat_raw = float(parts[0])
        lon_raw = float(parts[1])

        def _dms(v: float) -> float:
            av = abs(v)
            if av > 90:   # DMS compact: DDMMSS or DDDMMSS
                d  = int(av / 10000)
                m  = int((av % 10000) / 100)
                sc = av % 100
                dec = d + m / 60.0 + sc / 3600.0
                return -dec if v < 0 else dec
            return v

        lat = _dms(lat_raw)
        lon = _dms(lon_raw)
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except (ValueError, IndexError):
        pass
    return None, None


def _parse_video_date(raw: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw[:26], fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def read_video_meta(path: Path) -> dict:
    """
    Extract metadata from a video file via ffprobe.

    Returns a dict with keys compatible with read_exif():
      date, lat, lon, duration_s, width, height, codec,
      camera_make, camera_model
    """
    global _FFPROBE_OK
    if _FFPROBE_OK is None:
        _FFPROBE_OK = _check_ffprobe()

    empty: dict = {k: None for k in ("date", "lat", "lon", "duration_s",
                                      "width", "height", "codec",
                                      "camera_make", "camera_model")}
    if not _FFPROBE_OK:
        print("  [Video] WARNING: ffprobe not found — install ffmpeg: "
              "https://ffmpeg.org/download.html")
        return empty

    result = dict(empty)
    try:
        probe    = _ffprobe_json(path)
        fmt_tags = probe.get("format", {}).get("tags", {})
        tags_lc  = {k.lower(): v for k, v in fmt_tags.items()}

        # Date — Apple QuickTime tag > standard creation_time > file mtime
        for key in ("com.apple.quicktime.creationdate", "creation_time", "date"):
            raw_date = tags_lc.get(key)
            if raw_date:
                result["date"] = _parse_video_date(raw_date)
                if result["date"]:
                    break
        if not result["date"]:
            result["date"] = datetime.fromtimestamp(path.stat().st_mtime)

        # GPS — search format tags then each stream's tags (GoPro / DJI)
        def _gps_from_tags(tag_dict: dict) -> tuple[float | None, float | None]:
            lc = {k.lower(): v for k, v in tag_dict.items()}
            for key in ("location",
                        "com.apple.quicktime.location.iso6709",
                        "gps_coordinates", "gps", "location-eng", "coordinates"):
                raw = lc.get(key)
                if raw and isinstance(raw, str):
                    lat, lon = _parse_iso6709(raw)
                    if lat is not None:
                        return lat, lon
            return None, None

        lat, lon = _gps_from_tags(fmt_tags)
        if lat is None:
            for stream in probe.get("streams", []):
                lat, lon = _gps_from_tags(stream.get("tags", {}))
                if lat is not None:
                    break
        if lat is not None:
            result["lat"], result["lon"] = lat, lon

        # Duration
        dur = probe.get("format", {}).get("duration")
        if dur:
            result["duration_s"] = float(dur)

        # Video stream
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                result["width"]  = stream.get("width")
                result["height"] = stream.get("height")
                result["codec"]  = stream.get("codec_name")
                break

        # Camera / device
        result["camera_make"]  = (tags_lc.get("com.apple.quicktime.make") or
                                  tags_lc.get("make"))
        result["camera_model"] = (tags_lc.get("com.apple.quicktime.model") or
                                  tags_lc.get("model"))

    except Exception as e:
        print(f"  [Video] Metadata error for {path.name}: {e}")

    return result


def format_duration(seconds: float | None) -> str:
    """Return a human-readable duration string like '1h 23m 45s'."""
    if seconds is None:
        return "unknown"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:   return f"{h}h {m:02d}m {sec:02d}s"
    if m:   return f"{m}m {sec:02d}s"
    return f"{sec}s"
