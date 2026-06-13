# Hand Pointer Design

Date: 2026-06-13
Branch: hand-pointer
Status: Approved design, ready for implementation plan

## Goal

Let a user move and control the mouse pointer with one hand through the
webcam. The control pose is the ASL "U": index and middle fingers extended
and held together, ring and pinky curled. Bending the index left-clicks,
bending the middle right-clicks, and a thumb touch engages scroll. The
feature lives alongside the existing HandVol gesture controls and reuses the
capture, state, and dispatch flow.

## Core decisions (resolved during brainstorming)

1. **Anchor at the knuckles, show the cursor at the fingertips.** Track the
   midpoint of the index MCP (landmark 5) and middle MCP (landmark 9). These
   barely move when a fingertip curls, so the cursor holds still during a
   click. The cursor is then projected up to where the fingertips appear so
   the interaction feels touchscreen-like.

2. **Axis projection for the fingertip offset (method A), latched offset as
   fallback (method B).** The offset must come from stable landmarks, not the
   live fingertips, or the bend drift returns. Method A projects the cursor
   along the `wrist -> MCP-midpoint` axis by a hand-size-scaled distance.
   Method B (sample the real tip offset while fingers are straight, freeze it
   during a bend) is documented as a fallback if A feels off-position.

3. **Both screen mappers, default absolute.** An `AbsoluteMapper` maps a
   center sub-region of the frame to the full target monitor and snaps to the
   hand on first detection. A `RelativeMapper` moves the cursor by clutched
   deltas with no snap. Default is absolute. A flag and tray toggle switch
   between them.

4. **Primary monitor now, runtime switch later.** The target monitor is a
   config value defaulting to primary. A runtime switch gesture comes later
   once the user picks the gesture, so the code reads the target from config
   rather than hard-coding primary.

5. **Active region with margins.** MediaPipe needs the whole hand in frame, so
   the absolute mapper maps the center ~65% of the camera frame to 100% of the
   target monitor. Reaching a screen edge needs the hand only near the middle
   of the frame, keeping the whole hand visible. Margin is one tunable value.

6. **PIP joint angle for click detection.** A click is a finger bend, detected
   by the angle at the finger PIP joint (vectors `MCP->PIP` and `PIP->TIP`).
   The angle reads the same across hand tilt and self-normalizes for hand
   size. A Schmitt trigger (hysteresis) prevents one bend from chattering into
   multiple events.

7. **Faithful button up/down gives click, double-click, and drag for free.**
   Index bend sends left button down, straighten sends left button up. Middle
   bend maps to the right button. Windows interprets two quick pairs as a
   double-click and a held-down move as a drag, so no separate timing logic is
   needed.

8. **Scroll engages with a relaxed thumb touch.** While the U pose holds, the
   thumb pad touching the side or base of the index (near its knuckle) engages
   scroll. Index and middle stay straight so no clicks fire. Vertical hand
   movement scrolls while the touch holds. Releasing the thumb resumes
   pointing. Direction is configurable.

## Architecture

A `POINTER` mode that parallels the existing `SCRUB` mode in the capture ->
state -> dispatch flow. New code lives in a `handvol/handmouse/` package.

### New package: handvol/handmouse/

- `__init__.py`
- `detect.py` — U-sign detection and landmark geometry. Pure functions over
  MediaPipe landmarks. `capture.py` imports this and calls it inside
  `_resolve_hand`.
- `pointer.py` — anchor computation, axis projection, One-Euro smoothing, and
  the `PointerMapper` interface with `AbsoluteMapper` and `RelativeMapper`.
  Pure logic, no OS calls, unit-testable.
- `mouse.py` — OS injection. `move_to`, `left_down`, `left_up`, `right_down`,
  `right_up`, `scroll`, built on `ctypes` `SendInput`. Multi-monitor
  coordinate math lives here. A thin seam allows tests to assert calls without
  moving the real cursor.

### Edits to existing files

- `capture.py` — call `detect.detect_u_sign()` inside `_resolve_hand` before
  MediaPipe's `Victory`. Surface the pointer geometry the dispatch loop needs.
- `state.py` — add a `POINTER` state and pointer events.
- `handvol.pyw` — dispatch pointer events, own the active mapper and the
  target-monitor config, add CLI flags.
- `overlay.py` — draw the active region box, the cursor point, and click and
  scroll state for tuning.

## Detection details

### U sign

- Index and middle extended, ring and pinky curled.
- The two fingertips close together, with the tip-to-tip distance below a
  fraction of hand width, to separate the U from `Victory` (fingers spread).
- Extension is measured along the hand principal axis (`wrist -> MCP-midpoint`)
  rather than screen-Y, so a tilt up to 30 degrees toward the ASL "H" still
  reads as extended.
- Runs before `Victory` in `_resolve_hand`, so a fingers-together V becomes the
  pointer rather than Focus Spotify. A spread V still triggers Spotify.

### Backward-hand rejection

- Compute the hand-plane normal as the cross product of `wrist -> index_MCP`
  and `wrist -> pinky_MCP`.
- Combine the normal direction with MediaPipe handedness to reject the pose
  when the palm faces away from the camera.

### Hand selection

- Either hand works. The first hand forming the U drives the pointer.

## Cursor position

- Anchor = midpoint of index MCP (5) and middle MCP (9).
- Cursor point = anchor projected forward along the hand axis by
  `k * hand_scale`, where `hand_scale` derives from the wrist-to-MCP length.
  This is method A. Method B (latched offset) is the documented fallback.
- A One-Euro filter smooths the cursor point. It gives low lag during fast
  motion and steadiness when the hand is still, which suits a pointer better
  than a plain EMA.

### Mappers

- `AbsoluteMapper`: maps the center ~65% of the frame to the full target
  monitor. Snaps the cursor to the hand on first detection. Margin and target
  monitor are config values.
- `RelativeMapper`: each frame adds `gain * (current_point - last_point)` to
  the cursor. On re-acquisition of the U sign it resets `last_point` so the
  cursor resumes from its current spot (clutching), with no snap.
- Both implement a shared `map(point, just_acquired) -> (screen_x, screen_y)`
  interface. The active mapper is chosen by flag or tray toggle.

## Clicks, drag, double-click, scroll

- **Bend detection**: PIP joint angle with a Schmitt trigger. Engage when the
  angle drops below roughly 100 degrees, release when it rises above roughly
  130 degrees. Thresholds are tunable.
- **Buttons**: index bend = left button down, index straighten = left button
  up. Middle bend = right button down and up. Single click, double-click, and
  drag emerge from this faithful mapping. Windows owns the timing.
- **Scroll**: a relaxed thumb touch to the index base engages scroll. While
  held, vertical hand movement sends wheel events. Direction is configurable,
  defaulting to hand up = scroll up.

## State machine and coexistence

- New `POINTER` state, entered when the U sign holds about 5 frames (mirrors
  `SCRUB_ENTER_FRAMES`), exited when it drops about 3 frames (mirrors
  `SCRUB_EXIT_FRAMES`).
- While in `POINTER`, other HandVol gestures are suppressed so the cursor owns
  the hand, the same idea as the scrub lock.
- The existing `Number_9` lock takes priority. When locked, pointer mode does
  not engage.
- Clicks and scroll are sub-states handled inside `POINTER` and update every
  frame, so the toggle cooldown does not fight continuous control.

## OS injection

- `mouse.py` uses `ctypes` `SendInput` for low-latency moves and button
  events.
- Absolute moves use the 0..65535 normalized coordinate space over the virtual
  desktop. To target the primary monitor, the mapper converts a monitor-local
  position into virtual-desktop-normalized coordinates using the monitor
  rectangle and the virtual screen metrics (`SM_XVIRTUALSCREEN`,
  `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN`).
- A thin seam (an injectable sink) lets tests assert the intended calls without
  moving the real cursor.

## CLI flags

Mirror the existing flag style in `parse_args`:

- `--pointer-mode {absolute,relative}` (default `absolute`)
- `--pointer-margin` (active-region fraction, default ~0.65)
- `--pointer-sensitivity` (gain for relative mode)
- Existing tuning flags stay as they are.

## Testing

- `tests/test_pointer.py` (pure logic, no camera):
  - Axis projection math holds the cursor steady when a fingertip moves.
  - One-Euro filter smooths and tracks as expected.
  - `AbsoluteMapper` mapping and clamping, including the active-region margin
    and snap on first detection.
  - `RelativeMapper` delta accumulation and clutch reset on re-acquisition.
  - PIP-angle Schmitt trigger transitions (engage, hold, release).
  - U-sign detection separates from `Victory` and rejects a backward hand.
- `mouse.py` injection asserted through its seam without moving the cursor.
- Follows the existing test pattern. No GUI or camera tests.

## Out of scope (this version)

- The runtime monitor-switch gesture (config hook only for now).
- Spanning both monitors as one mapping target.
- Gesture customization UI.
