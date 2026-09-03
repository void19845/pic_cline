from __future__ import annotations
"""
organizer.i18n
==============
Lightweight internationalisation module.

Usage
-----
    from organizer.i18n import t, set_language, detect_language, available_languages

    # Auto-detect OS language at startup
    set_language(detect_language())

    # Translate a key (with optional format kwargs)
    label = t("btn_run")                       # "Run" / "Lancer" / ...
    msg   = t("faces_count", n=12)             # "12 label(s) loaded"

    # Change language at runtime (hot-reload, no restart needed)
    set_language("fr")

Hot-reload contract
-------------------
When set_language() is called, it fires every registered callback with
the new language code.  The UI registers callbacks that update its
tk.StringVar instances, so widgets retranslate without being recreated.

    from organizer.i18n import on_language_change
    on_language_change(lambda code: my_var.set(t("some_key")))

Locale files
------------
JSON files at  <package_root>/../locales/<code>.json
e.g.  locales/en.json, locales/fr.json, locales/es.json, locales/ja.json

Each file must contain a "_meta" key:
    { "_meta": { "lang": "Français", "code": "fr" }, ... }
"""

import json
import locale
import os
from pathlib import Path
from typing import Callable

# ── Paths ─────────────────────────────────────────────────────────────────────
_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_FALLBACK     = "en"

# ── Runtime state ─────────────────────────────────────────────────────────────
_current_code:  str        = _FALLBACK
_strings:       dict       = {}          # active translation table
_callbacks:     list[Callable[[str], None]] = []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load(code: str) -> dict:
    """Load and return the translation dict for *code*, falling back to en."""
    path = _LOCALES_DIR / f"{code}.json"
    if not path.exists():
        path = _LOCALES_DIR / f"{_FALLBACK}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[i18n] Could not load {path}: {e}")
        return {}


def _merge_with_fallback(code: str) -> dict:
    """Return translation dict merged with English fallback for missing keys."""
    base    = _load(_FALLBACK)
    overlay = _load(code) if code != _FALLBACK else {}
    return {**base, **overlay}


# ── Public API ────────────────────────────────────────────────────────────────

def detect_language() -> str:
    """
    Detect the OS UI language and return the closest supported locale code.
    Falls back to 'en' if no match is found.
    """
    supported = {p.stem for p in _LOCALES_DIR.glob("*.json")
                 if not p.stem.startswith("_")}

    # 1. LANG / LANGUAGE env vars (Unix)
    for env_var in ("LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES"):
        raw = os.environ.get(env_var, "")
        if raw:
            code = raw.split(":")[0].split(".")[0].split("_")[0].lower()
            if code in supported:
                return code

    # 2. locale.getdefaultlocale() (cross-platform)
    try:
        loc, _ = locale.getdefaultlocale()
        if loc:
            code = loc.split("_")[0].lower()
            if code in supported:
                return code
    except Exception:
        pass

    # 3. Windows UI language via winreg
    try:
        import winreg
        key  = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r"Control Panel\International")
        lang = winreg.QueryValueEx(key, "LocaleName")[0]  # e.g. "fr-FR"
        code = lang.split("-")[0].lower()
        if code in supported:
            return code
    except Exception:
        pass

    return _FALLBACK


def set_language(code: str) -> None:
    """
    Load the translation table for *code* and fire all registered callbacks.
    Safe to call from any thread (callbacks run on the calling thread).
    """
    global _current_code, _strings
    _current_code = code
    _strings      = _merge_with_fallback(code)
    for cb in _callbacks:
        try:
            cb(code)
        except Exception as e:
            print(f"[i18n] Callback error: {e}")


def current_language() -> str:
    """Return the active language code (e.g. 'fr')."""
    return _current_code


def t(key: str, **kwargs) -> str:
    """
    Translate *key* using the active language.

    Supports Python str.format() placeholders:
        t("faces_count", n=5)  ->  "5 label(s) loaded"

    Returns the key itself if no translation is found.
    """
    raw = _strings.get(key, key)
    if kwargs:
        try:
            return raw.format(**kwargs)
        except (KeyError, IndexError):
            return raw
    return raw


def on_language_change(callback: Callable[[str], None]) -> None:
    """Register a callback invoked whenever set_language() is called."""
    _callbacks.append(callback)


def remove_callback(callback: Callable[[str], None]) -> None:
    """Unregister a previously registered callback."""
    try:
        _callbacks.remove(callback)
    except ValueError:
        pass


def available_languages() -> list[dict]:
    """
    Return a sorted list of available languages as dicts:
        [{"code": "en", "lang": "English"}, ...]
    """
    langs = []
    for path in sorted(_LOCALES_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            langs.append({
                "code": meta.get("code", path.stem),
                "lang": meta.get("lang", path.stem),
            })
        except Exception:
            pass
    return langs


# ── Bootstrap: load English by default so t() works before set_language() ────
_strings = _merge_with_fallback(_FALLBACK)
