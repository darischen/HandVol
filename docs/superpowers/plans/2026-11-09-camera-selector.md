# Camera Source Selector Plan

Spec: none (requirements come from the user request, quoted below).

> "are we able to add like a source selector to the right click menu? hover over
> the option and a new list will expand ... it'll list all camera sources and
> you're able to choose which one you want"

## Background (verified on the dev machine, 2026-11-09)

HandVol opens `cv2.VideoCapture(args.cam, cv2.CAP_DSHOW)` with `--cam` defaulting
to 0. DirectShow enumerates on this machine as:

| index | name | frames |
|---|---|---|
| 0 | `Daris's S25 Ultra (Windows Virtual Camera)` (Phone Link) | opens, all black |
| 1 | `NexiGo N60 FHD Webcam` | real image |
| 2 | `Camera (NVIDIA Broadcast)` | black |
| 3 | `OBS Virtual Camera` | OBS placeholder |

The Phone Link camera stays registered after the phone disconnects, holds
index 0, and feeds black frames, so HandVol runs but sees nothing.

## Global Constraints

- Test interpreter: `C:/Python314/python.exe -m pytest -q` from the repo root. Baseline: 91 passed.
- No new pip dependencies. Use `comtypes` (already in requirements.txt).
- DirectShow enumeration order MUST match OpenCV `CAP_DSHOW` indices. The menu stores an index; names are for display and persistence.
- Persist the chosen camera by NAME (indices shift when devices come and go) in `%APPDATA%\HandVol\settings.json` under key `"camera_name"`.
- Startup selection priority: explicit `--cam N` > saved `camera_name` (if currently present) > first camera whose name does not contain `virtual camera` (case-insensitive) > 0.
- Every failure in enumeration or settings I/O degrades silently (empty list / empty dict / skipped save with a printed `[handvol] ...` line). The app must never crash on these paths.
- Hardware-free tests only. Do not open cameras or call real COM in tests.

## Task 1: `cameras` and `settings` modules with tests

Files: create `handvol/cameras.py`, `handvol/settings.py`, `tests/test_cameras.py`, `tests/test_settings.py`.

### `handvol/cameras.py` (write this code)

```python
"""Enumerate DirectShow video capture devices.

The order matches OpenCV's CAP_DSHOW device indices, so list position i is
the index to pass to cv2.VideoCapture(i, cv2.CAP_DSHOW).
"""

import ctypes
from ctypes import POINTER, HRESULT, byref, c_ulong, c_void_p
from ctypes.wintypes import DWORD

# Substring (lowercase) marking software cameras that usually feed nothing
# useful by default: Windows Phone Link ("Windows Virtual Camera") and OBS.
VIRTUAL_MARKERS = ("virtual camera",)


def _enumerate_dshow():
    import comtypes
    from comtypes import COMMETHOD, GUID, IUnknown, CoCreateInstance
    from comtypes.automation import VARIANT

    clsid_system_device_enum = GUID("{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}")
    clsid_video_input_category = GUID("{860BB310-5D01-11d0-BD3B-00A0C911CE86}")

    class IPropertyBag(IUnknown):
        _iid_ = GUID("{55272A00-42CB-11CE-8135-00AA004BB851}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Read",
                      (["in"], ctypes.c_wchar_p, "name"),
                      (["in"], POINTER(VARIANT), "var"),
                      (["in"], c_void_p, "log")),
            COMMETHOD([], HRESULT, "Write",
                      (["in"], ctypes.c_wchar_p),
                      (["in"], POINTER(VARIANT))),
        ]

    class IMoniker(IUnknown):
        _iid_ = GUID("{0000000f-0000-0000-C000-000000000046}")
        # IPersist + IPersistStream slots precede BindToStorage; they are
        # declared only to keep the vtable offsets right.
        _methods_ = [
            COMMETHOD([], HRESULT, "GetClassID", (["out"], POINTER(GUID))),
            COMMETHOD([], HRESULT, "IsDirty"),
            COMMETHOD([], HRESULT, "Load", (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "Save", (["in"], c_void_p), (["in"], ctypes.c_int)),
            COMMETHOD([], HRESULT, "GetSizeMax", (["out"], POINTER(ctypes.c_ulonglong))),
            COMMETHOD([], HRESULT, "BindToObject",
                      (["in"], c_void_p), (["in"], c_void_p),
                      (["in"], POINTER(GUID)), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "BindToStorage",
                      (["in"], c_void_p), (["in"], c_void_p),
                      (["in"], POINTER(GUID)), (["out"], POINTER(POINTER(IUnknown)))),
        ]

    class IEnumMoniker(IUnknown):
        _iid_ = GUID("{00000102-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Next",
                      (["in"], c_ulong, "celt"),
                      (["out"], POINTER(POINTER(IMoniker)), "rgelt"),
                      (["out"], POINTER(c_ulong), "fetched")),
        ]

    class ICreateDevEnum(IUnknown):
        _iid_ = GUID("{29840822-5B84-11D0-BD3B-00A0C911CE86}")
        _methods_ = [
            COMMETHOD([], HRESULT, "CreateClassEnumerator",
                      (["in"], POINTER(GUID)),
                      (["out"], POINTER(POINTER(IEnumMoniker))),
                      (["in"], DWORD)),
        ]

    try:
        comtypes.CoInitialize()
    except OSError:
        pass  # already initialized on this thread in another mode
    dev_enum = CoCreateInstance(clsid_system_device_enum, interface=ICreateDevEnum)
    enum = dev_enum.CreateClassEnumerator(byref(clsid_video_input_category), 0)
    names = []
    if not enum:  # S_FALSE: no devices in the category
        return names
    while True:
        try:
            moniker, fetched = enum.Next(1)
        except comtypes.COMError:
            break
        if not fetched:
            break
        bag = moniker.BindToStorage(
            None, None, byref(IPropertyBag._iid_)).QueryInterface(IPropertyBag)
        var = VARIANT()
        bag.Read("FriendlyName", byref(var), None)
        names.append(str(var.value))
    return names


def list_cameras():
    """Return camera friendly names in CAP_DSHOW index order ([] on failure)."""
    try:
        return _enumerate_dshow()
    except Exception as exc:  # COM / ctypes failures must never crash the app
        print(f"[handvol] camera enumeration failed: {exc!r}")
        return []


def is_virtual(name):
    lowered = name.lower()
    return any(marker in lowered for marker in VIRTUAL_MARKERS)


def choose_camera(names, saved_name=None, cli_index=None):
    """Pick the startup camera index.

    Priority: explicit CLI index > saved name (if present now) > first
    non-virtual camera > 0. Duplicate names resolve to the first match.
    """
    if cli_index is not None:
        return cli_index
    if saved_name and saved_name in names:
        return names.index(saved_name)
    for i, name in enumerate(names):
        if not is_virtual(name):
            return i
    return 0
```

### `handvol/settings.py` (write this code)

```python
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
```

### Tests

`tests/test_cameras.py` (pure functions only, never call `list_cameras` for real):

- `choose_camera(["Phone (Windows Virtual Camera)", "NexiGo N60 FHD Webcam"])` → 1
- `choose_camera(names, saved_name="NexiGo N60 FHD Webcam")` where names = `["A (Windows Virtual Camera)", "OBS Virtual Camera", "NexiGo N60 FHD Webcam"]` → 2
- saved name missing from the list falls through to first non-virtual
- `cli_index=3` wins over a present saved name → 3
- all virtual → 0; empty list → 0
- duplicate names: `choose_camera(["Cam", "Cam"], saved_name="Cam")` → 0
- `is_virtual("OBS Virtual Camera")` True, `is_virtual("Camera (NVIDIA Broadcast)")` False
- `list_cameras()` returns `[]` and does not raise when `_enumerate_dshow` is monkeypatched to raise `OSError("boom")`

`tests/test_settings.py` (use `tmp_path`):

- `load` on missing file → `{}`
- `load` on malformed JSON → `{}`; on a JSON list `[1,2]` → `{}`
- `update({"camera_name": "X"}, p)` then `load(p)` → `{"camera_name": "X"}`; parent dir created when absent
- `update` merges: existing `{"a": 1}` plus `update({"b": 2})` → `{"a": 1, "b": 2}`
- `update` returns False and does not raise when the target path's parent is an existing FILE (mkdir fails)

Also verify by hand once (not as a pytest): `C:/Python314/python.exe -c "from handvol.cameras import list_cameras; print(list_cameras())"` prints the four names in the table above, in that order.

Commit: `feat(camera): add DirectShow camera enumeration and settings store`

## Task 2: Tray "Camera" submenu wired to the capture worker

Files: modify `handvol.pyw`, `README.md`.

1. `parse_args`: change `--cam` to `type=int, default=None`, help: `"Webcam index; overrides the camera saved from the tray menu"`.
2. `main()`: after `parse_args`, build a shared holder
   `camera = {"names": cameras.list_cameras(), "index": ...}` with
   `index = cameras.choose_camera(names, settings.load().get("camera_name"), args.cam)`.
   Print `[handvol] camera: <index> <name or '?'>` once.
3. `capture_loop`: take the `camera` holder as a new parameter (after `pointer_mode`) and open `GestureSource(cam_index=camera["index"])` instead of `args.cam`. `start_worker` passes it.
4. Tray menu: insert `MenuItem("Camera", Menu(camera_items))` directly above `"Pause"`. `camera_items` is a zero-arg function returning the item list (pystray calls it each time it rebuilds the menu):
   - one radio item per name, `checked=lambda item, i=i: camera["index"] == i`, `radio=True`
   - if `names` is empty: a single disabled item `"No cameras found"`
   - then `Menu.SEPARATOR` and `MenuItem("Refresh list", on_refresh_cameras)`
5. Selecting camera `i`:
   - no-op if `i == camera["index"]`
   - set `camera["index"] = i`; `settings.update({"camera_name": names[i]})`
   - if not paused: `stop_worker()` then `start_worker()` (the preview window state in `show_evt` carries over)
   - `icon.update_menu()`
6. `refresh_cameras()` helper (used by "Refresh list" and by resume-from-pause in `on_pause` before `start_worker()`): re-run `list_cameras()`; if the currently selected name exists in the new list, move `camera["index"]` to its new position; otherwise keep the index. Store the new names, then `icon.update_menu()`. It never restarts the worker.
7. README: in the tray section, add a bullet for the *Camera* submenu (lists every camera, the choice is remembered in `%APPDATA%\HandVol\settings.json`, *Refresh list* rescans after plugging in or connecting a phone). Update the `--cam` row: overrides the saved tray choice. Add a short note: Windows Phone Link registers "Windows Virtual Camera" which stays listed after the phone disconnects; HandVol skips virtual cameras on first run.

Testing: the existing suite plus Task 1's tests must still pass. Do NOT launch
`handvol.pyw` (it drives the real mouse, keyboard, and shutdown gestures); the
controller does the live check. Verify the file compiles with
`C:/Python314/python.exe -m py_compile handvol.pyw`.

Commit: `feat(tray): add Camera submenu to pick and remember the capture source`
