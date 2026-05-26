# Tray Pause Feature — Design

## Goal

Add a "Pause" item to the tray icon's right-click menu that completely
stops gesture recognition and releases the webcam so other applications
(Zoom, OBS, etc.) can use it. Resuming spins the worker back up.

## User-facing behavior

- **Right-click tray icon** → menu shows `Show preview`, `Pause`, `Quit`.
- **Click "Pause"** → checkmark appears; camera is released within ~1 frame;
  preview window (if open) closes; tray glyph dims to gray.
- **Click "Pause" again** → checkmark clears; worker restarts; tray glyph
  returns to normal white digits after MediaPipe's ~1s warmup.
- **Left-click tray icon** → unchanged; still toggles `Show preview`.
- If the preview was open when pausing, it does NOT reopen on resume —
  the user must re-enable it manually.

## Architecture

### Lifecycle ownership

Today `main()` creates a single worker thread and a single `quit_evt`.
After this change, `main()` owns helper closures that can stop and
restart the worker any number of times:

```
start_worker()  → creates a fresh stop event + Thread, starts it
stop_worker()   → sets stop event, joins thread (timeout=2.0), idempotent
```

The worker's loop condition changes from `while not quit_evt.is_set()`
to `while not worker_stop.is_set()`, where `worker_stop` is a per-worker
event passed in at construction.

### Pause state

A single `paused` flag (plain bool held in `main`'s closure, mutated
inside the pystray callback — pystray callbacks run on its own thread,
but the flag is only read/written from that thread plus once from quit,
so a lock isn't needed).

### Menu

```python
Menu(
    MenuItem("Show preview", on_toggle, default=True,
             checked=lambda i: show_evt.is_set()),
    MenuItem("Pause", on_pause,
             checked=lambda i: paused["v"]),
    MenuItem("Quit", on_quit),
)
```

`paused` is a one-key dict so the closure can mutate it without
`nonlocal` gymnastics across nested handlers.

### Pause handler

```
on_pause:
    if paused["v"]:               # currently paused → resume
        paused["v"] = False
        start_worker()
    else:                          # currently running → pause
        paused["v"] = True
        show_evt.clear()           # close the preview too
        stop_worker()              # releases camera via GestureSource.__exit__
        # Snapshot the last known volume so the dimmed glyph is informative.
        try:
            vol = int(round(audio.get_volume()))
        except Exception:
            vol = 0
        icon.icon = make_volume_image(vol, dimmed=True)
```

### Quit handler

```
on_quit:
    stop_worker()        # no-op if already paused
    icon.stop()
```

The `quit_evt` global goes away — main's bottom `quit_evt.set()` /
`worker.join()` lines are absorbed into `stop_worker()`.

### Dimmed icon

`make_volume_image(level, dimmed=False)` — when `dimmed=True`, draw text
with `fill=(128, 128, 128, 180)` instead of `(255, 255, 255, 255)`.
No other changes; the layout/size stays identical so the icon doesn't
shift in the tray.

## Files touched

- `handvol.pyw` only.
  - `make_volume_image` — add `dimmed` parameter.
  - `main` — extract `start_worker`/`stop_worker`, add `on_pause`,
    add menu item, simplify shutdown path.
  - `capture_loop` — change loop condition argument name from
    `quit_evt` to `worker_stop`. No other behavior changes.

## Non-goals

- No hotkey for pause (menu-only).
- No persistence — paused state resets on app restart (app starts
  unpaused, matching today's behavior).
- No automatic pause/resume based on camera contention from other apps.

## Edge cases

- **Pause spam:** `stop_worker()` is idempotent (sets an already-set
  event, joins an already-dead thread). The checkable menu item
  visually rate-limits user input anyway.
- **Quit while paused:** `stop_worker()` no-ops, `icon.stop()` exits
  the message pump, process ends cleanly.
- **Resume races with a stale icon update:** after `start_worker()`
  the new worker's first frame (~1s later) overwrites the dimmed
  glyph. In between, the dimmed glyph stays visible — desired.
- **MediaPipe model failure on resume:** worker raises and dies; tray
  remains showing the dimmed glyph. Acceptable for v1; user can quit
  and relaunch. (No new failure modes introduced beyond what already
  exists on first launch.)
