# HandVol

Gesture-controlled Windows volume + media using a webcam and MediaPipe.
Pinch your thumb and index in an OK sign to scrub volume, close your fist
to mute, open your palm to play/pause, sideways thumbs to skip tracks, and
number gestures (1-10) formed with two hands. Hold a middle finger for 5 seconds
to restart your PC, or double middle finger to shut it down. Make an ASL "U"
to drive the mouse pointer with clicks, drag, and scroll (see
[Hand Mouse Pointer](#hand-mouse-pointer)).

| Gesture | Action |
|---|---|
| 👌 OK sign | Hold and move up/down to scrub volume |
| ✊ Closed fist | Toggle mute |
| ✋ Open palm | Toggle play/pause |
| ✌️ Victory | Focus Spotify (launch it if not running) |
| 🤟 ILoveYou | Close Spotify |
| 👉 Thumb sideways → right | Next track (works for either hand) |
| 👈 Thumb sideways → left | Previous track (works for either hand) |
| 🤘 Hang loose sign | Pause app & release camera |
| **Number gestures (two hands)** | **Display recognized number 1-10** |
| Fist + Pointer | Number 1 — Focus first Chrome window (Win+1; launch Chrome if not running) |
| Fist + Victory | Number 2 — Cycle to second Chrome window (Win+1 twice) |
| Fist + 3 fingers | Number 3 — Focus Discord (launch it if not running) |
| Fist + 4 fingers | Number 4 — Focus VS Code (launch it if not running) |
| Fist + Open palm | Number 5 — Open Task Manager (Ctrl+Shift+Esc) |
| Open palm + Pointer | Number 6 — Voice search (focus Chrome, Ctrl+T, dictate, auto-Enter after 1s silence; say "go to <domain>" for popular links) |
| Open palm + Victory | Number 7 — Text input field (type directly into active field) |
| Open palm + 4 fingers | Number 9 — Lock Gesture |
| Open palm + Open palm | Number 10 — Close active window (Alt+F4) |
| 3 extended fingers | Ctrl+W — Close active tab |
| 4 extended fingers | Ctrl+Tab — Cycle to next tab |
| ✌️ "U" sign (index + middle up, held together) | Hand mouse pointer: move the cursor, click, drag, scroll (see [Hand Mouse Pointer](#hand-mouse-pointer)) |
| 🖕 Single middle finger (3s hold) | **Restart Windows** |
| 🖕🖕 Double middle finger (3s hold) | **Shut down Windows** |

Direction is reported in your real-world frame: thumb tip toward your
right = next, toward your left = previous, regardless of which hand.

No model training, no cloud calls, no per-app permissions. Runs locally
off the pretrained MediaPipe Gesture Recognizer, with custom
landmark-based detection layered on top for the OK sign and sideways
thumbs.

## Extra Features

**Lock State:** When the lock icon displays red in the overlay, gesture
execution is blocked to prevent accidental actions. Gestures are still
recognized, allowing number_9 (nine fingers) to toggle the lock
even when active. Use this before focusing on other tasks or when you
don't want HandVol responding to your hands.

**Camera Release:** The hang loose sign (shaka) pauses the app and releases
the camera, or use the *Pause* option in the tray menu. Useful before
joining video calls or when another app needs camera access. Resume by
toggling the pause state again.

**Voice Search:** Form `number_6` (open palm + pointer) to focus Chrome,
open a new tab, and start dictating. Your speech is transcribed locally
with `faster-whisper` (`small.en`, int8, CPU) — no cloud calls. The tray
icon turns into a red microphone and HandVol auto-locks gestures while
recording. After 1 second of silence, the transcript is typed into the
URL bar and Enter fires automatically. Say "go to <domain>" to navigate
directly to popular sites (e.g., "go to GitHub" → github.com). If no
speech is detected within ~5 seconds, the trigger times out cleanly with
no typing.

First invocation downloads the `small.en` model (~460 MB) into the
HuggingFace cache.

## Hand Mouse Pointer

Control the mouse with one hand. Make the ASL "U": index and middle
fingers extended and held **together** (close, not spread like Victory),
palm facing the camera. After about 5 frames HandVol enters pointer mode,
the cursor snaps to your hand, and a cyan box plus a crosshair appear in
the preview.

**Moving.** The cursor tracks a point projected from your wrist and
knuckles up to where your fingertips are, so it stays steady when you bend
a finger to click. Sideways tilt up to about 30 degrees still works.

**Clicking, drag, double-click.** Hook your **index** fingertip down to
left-click, your **middle** fingertip to right-click. The click is a
comfortable half-bend, not a full curl. Button up/down is sent faithfully,
so a quick hook is a click, two quick hooks are a double-click, and holding
the hook while moving is a drag. The cursor is pinned in place the instant a
click fires, so it lands exactly on target; moving past a small deadzone
turns the hold into a drag.

**Scrolling.** Raise your **thumb** straight up to engage scroll. The spot
where you engaged becomes an anchor (shown as a horizontal bar with a
tracking dot, like the volume control). Move your hand above the anchor to
scroll up, below to scroll down. Speed is proportional to the distance from
the anchor. Lower the thumb to resume pointing.

**Reach.** Only the center of the camera frame maps to the screen, so your
whole hand stays in view while still reaching every edge. The active region
is shifted up by default so the taskbar is reachable without dropping your
hand out of frame.

**Modes.** The default is absolute mapping (hand position = cursor
position). The tray menu's **Trackpad mode** switches to relative mapping:
the cursor moves by hand deltas and you clutch (drop the U, reposition,
re-make it) to cover distance, like lifting a finger off a laptop trackpad.

While the pointer feature is enabled, the Pointing_Up (toggle preview) and
middle-finger (restart/shutdown) gestures are suppressed, since those poses
double as click poses.

On a dual-monitor setup the pointer targets the primary monitor.

## Requirements

- Windows 10/11
- Python 3.11+
- A USB webcam (built for the NexiGo 1080p, works with anything DirectShow-compatible)

## Setup

Install dependencies directly into your system Python (no virtualenv):

```powershell
# from the repo root
pip install -r requirements.txt
```

## Run

```powershell
python handvol.pyw
```

HandVol installs a **system-tray icon** (bottom-right, in the hidden-icon
overflow on a fresh Windows install — drag it onto the taskbar to pin).

- **Left-click the tray icon** → toggle the OpenCV preview window on/off.
- **Right-click** → menu with *Show preview* (checked when visible),
  *Pause* (releases the camera; useful before joining a virtual meeting),
  and *Quit*.
- **Esc** inside the preview window also hides it.
- To quit, use the tray's *Quit* item (or kill `pythonw.exe` from Task Manager).

By default it starts tray-only (no window). Pass `--show` to launch with
the preview already open.

**Hold gesture feedback:** When you hold a middle finger (or double middle finger),
the preview overlay displays a red timer showing elapsed time and the action it
will trigger (e.g., `RESTART 2.3s / 3.0s`). The action fires once you hold for
the full 3.0 seconds.

### Useful flags

| Flag | What it does |
|---|---|
| `--sensitivity 80` | Volume points per full-frame vertical travel. Higher = faster scrub. |
| `--smoothing 0.3` | EMA factor on pinch position. Lower = laggier, higher = jitterier. |
| `--cam 0` | Webcam index, if you have more than one. |
| `--debug` | Print frame-by-frame state and scrub values. |
| `--no-audio` | Skip all pycaw/media calls — overlay only, for tuning. |
| `--show` | Start with the preview window already open (otherwise tray-only). |

**Hand mouse pointer flags:**

| Flag | What it does |
|---|---|
| `--no-pointer` | Disable the hand mouse pointer feature entirely. |
| `--pointer-mode {absolute,relative}` | Mapping mode at startup. Relative is also toggleable from the tray (*Trackpad mode*). Default `absolute`. |
| `--pointer-margin 0.65` | Fraction of the camera frame that maps to the screen (absolute mode). |
| `--pointer-lift 0.15` | Shift the active region up by this fraction so the screen bottom is easier to reach. |
| `--pointer-gain 2.0` | Cursor gain for relative/trackpad mode. |
| `--pointer-k 1.0` | How far the cursor projects toward the fingertips, as a multiple of hand size. Lower = steadier but lower. |
| `--click-engage 1.5` | Fingertip-curl ratio below which a click fires (straight finger ≈ 2; lower = must curl more). |
| `--click-release 1.7` | Curl ratio above which a click releases. Keep above `--click-engage` for clean latching. |
| `--scroll-gain 60` | Scroll speed (wheel notches per unit hand displacement per second). |
| `--scroll-invert` | Invert scroll direction. |
| `--scroll-thumb-ratio 1.68` | Thumb extension needed to engage scroll. Higher = thumb must be raised more. |

## Installation

An NSIS installer is available for easy installation and updates. The installer
automatically detects and removes old versions before installing the new one,
ensuring a clean upgrade path.

## Launch silently at startup

1. Press `Win+R`, type `shell:startup`, Enter.
2. Right-click → New → Shortcut → browse to `handvol_startup.vbs` in this repo.
3. Next login, HandVol runs hidden. Quit anytime via the tray icon.

The `.vbs` shim invokes `pythonw.exe` so no console window flashes.

## Project layout

```
handvol/
├── capture.py        Webcam + MediaPipe LIVE_STREAM + custom OK/side-thumb detection
├── scrubber.py       Pure-logic volume scrubber (anchor + EMA)
├── state.py          IDLE / SCRUB / IDLE_COOLDOWN debouncer
├── audio.py          pycaw wrapper (volume + mute)
├── media.py          Media play/pause and track-skip keys
├── spotify.py        Focus/launch/close Spotify via Win32
├── discord.py        Focus/launch Discord via Win32 + Squirrel updater
├── vscode.py         Focus/launch VS Code via Win32 + known install paths
├── taskbar.py        Synthesize Win+N taskbar shortcuts (used for Chrome)
├── overlay.py        OpenCV drawing helpers
├── handmouse/        Hand mouse pointer package
│   ├── detect.py     U-sign detection, knuckle geometry, fingertip-curl, thumb-raise
│   ├── pointer.py    One-Euro smoothing, absolute/relative mappers, click + scroll logic
│   └── mouse.py      SendInput cursor injection + multi-monitor coordinate math
├── face_detect.py    MediaPipe Face Landmarker wrapper + landmark-to-embedding helper
├── face_profile.py   On-disk face identity profile (cosine similarity matching)
└── calibration.py    Standalone face calibration UI (~20 pose captures)
handvol.pyw           Entry point: argparse, tray icon, capture loop, event dispatch
tests/
├── test_scrubber.py          Unit tests for scrubber + state machine
├── test_handmouse_detect.py  Unit tests for U-sign detection + hand geometry
├── test_pointer.py           Unit tests for filter, mappers, click + scroll logic
├── test_pointer_state.py     Unit tests for the POINTER state transitions
├── test_mouse.py             Unit tests for coordinate math + injection sequencing
├── test_face_embedding.py    Unit tests for landmark-to-embedding helper
└── test_face_profile.py      Unit tests for FaceProfile save/load + matching
```

### Gesture detection internals

MediaPipe's built-in classifier handles `Closed_Fist`, `Open_Palm`,
`Victory`, and `ILoveYou` directly. Custom landmark-based detection in
`capture.py` covers:

- **OK sign:** thumb tip touches index tip; middle, ring, pinky extended.
- **Sideways thumb:** thumb extended horizontally with the other four
  fingers curled into a fist. Direction comes from the thumb-tip x
  relative to the thumb base; hand identity comes from MediaPipe's
  handedness (with the convention inverted because the frame is
  pre-mirrored for selfie view).
- **Hang loose sign:** thumb and pinky extended, other three fingers
  curled into a fist. Triggers pause/resume and camera release.
- **"U" sign (pointer):** index and middle extended and held together,
  ring and pinky curled, palm facing the camera. Runs before Victory so a
  fingers-together V drives the pointer instead of focusing Spotify. Clicks
  come from a fingertip-curl ratio, never from gesture labels, so a click
  pose cannot trip the restart or toggle-preview gestures. Tuning constants
  live in `handvol/handmouse/detect.py` and `handvol/handmouse/pointer.py`.

The lock icon in the overlay indicates the current lock state (unlocked
by default). Lock state is toggled via number_9 (double middle finger)
and blocks all gesture-triggered actions while still recognizing gestures
in the frame.

Tuning constants for the landmark checks live at the top of
`handvol/capture.py`.

## Testing

```powershell
python -m pytest tests/ -q
```

The scrubber and state machine are pure logic and tested without a
webcam.

## Troubleshooting

- **`Could not open camera index 0`** — another app has the camera, or
  Windows Camera privacy settings are blocking desktop apps. Try
  `--cam 1`.
- **`AudioDevice has no attribute Activate`** — pycaw version mismatch.
  The code handles both old and new pycaw via `_dev` fallback; make
  sure you're on the version pinned in `requirements.txt`.
- **Media key does nothing** — the `keyboard` library needs admin on
  some Windows configs. Run from an elevated terminal, or `pyautogui`
  will be tried as fallback if installed.
- **Tray icon missing** — Windows hides new tray icons in the overflow
  by default. Click the `^` chevron in the taskbar and drag the HandVol
  icon onto the visible area to pin it.
- **Side-thumb skip/prev firing the wrong direction** — extremely
  unlikely, but if MediaPipe's handedness convention differs on your
  build, swap the `hand_prefix` mapping in
  `handvol/capture.py::_detect_side_thumb`.
