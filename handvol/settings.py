"""Tiny JSON settings store at %APPDATA%\\HandVol\\settings.json."""

import json
import os
from pathlib import Path

SETTINGS_PATH = Path(os.environ.get("APPDATA") or Path.home()) / "HandVol" / "settings.json"


def load(path=None):
    """Return the settings dict, or {} if missing, unreadable, or malformed."""
    path = Path(path or SETTINGS_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update(changes, path=None):
    """Merge `changes` into the stored settings and write atomically.

    Returns True on success, False (after printing) on I/O failure.
    """
    path = Path(path or SETTINGS_PATH)
    data = load(path)
    data.update(changes)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[handvol] could not save settings: {exc!r}")
        return False
    return True
