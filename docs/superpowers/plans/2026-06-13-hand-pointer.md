# Hand Pointer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one hand control the mouse pointer through the webcam using the ASL "U" pose, with index/middle bends as left/right clicks, drag and double-click for free, and a thumb-touch scroll.

**Architecture:** A new `POINTER` mode parallels the existing `SCRUB` mode in the capture -> state -> dispatch flow. Pure detection and pointer math live in a new `handvol/handmouse/` package (`detect.py`, `pointer.py`); OS cursor injection lives in `handvol/handmouse/mouse.py`. The dispatch loop in `handvol.pyw` drives them. Clicks come from landmark geometry, not gesture labels, so click poses never mis-fire existing gestures.

**Tech Stack:** Python 3.11, MediaPipe normalized landmarks, ctypes `SendInput` (Windows), pytest.

---

## File structure

New package `handvol/handmouse/`:

- `__init__.py` — empty package marker.
- `detect.py` — pure landmark geometry and pose detection: `mcp_midpoint`, `hand_axis`, `hand_scale`, `projected_point`, `pip_angle`, `hand_normal_z`, `palm_facing`, `detect_u_sign`, `thumb_touch`.
- `pointer.py` — `OneEuroFilter`, `AbsoluteMapper`, `RelativeMapper`, `BendTrigger`, and the `HandPointer` orchestrator returning a `PointerAction`.
- `mouse.py` — `Monitor`, `VirtualScreen`, `to_absolute`, `get_primary_monitor`, `get_virtual_screen`, `Mouse` (injectable sink seam).

Edited existing files:

- `handvol/capture.py` — call `detect.detect_u_sign` in `_resolve_hand`, emit `"U_sign"`.
- `handvol/state.py` — add `POINTER` state, `U_SIGN` constant, pointer events, sticky-pose maintenance.
- `handvol.pyw` — dispatch pointer events, build `HandPointer` + `Mouse`, add CLI flags.
- `handvol/overlay.py` — draw active region, cursor point, click/scroll state.

New tests:

- `tests/test_handmouse_detect.py` — `detect.py` geometry and pose detection.
- `tests/test_pointer.py` — `pointer.py` filter, mappers, trigger, orchestrator.
- `tests/test_mouse.py` — `to_absolute` math and `Mouse` sequencing via sink.
- `tests/test_pointer_state.py` — `state.py` POINTER transitions.

Run all tests with: `python -m pytest -q`

---

## Task 1: Package skeleton and geometry primitives

**Files:**
- Create: `handvol/handmouse/__init__.py`
- Create: `handvol/handmouse/detect.py`
- Create: `tests/test_handmouse_detect.py`

- [ ] **Step 1: Create the empty package marker**

Create `handvol/handmouse/__init__.py` with a single comment line:

```python
# handmouse: hand-controlled mouse pointer (U-sign pose detection + pointer math).
```

- [ ] **Step 2: Write the failing test for the landmark helper and geometry primitives**

Create `tests/test_handmouse_detect.py`:

```python
import math

from handvol.handmouse import detect


class LM:
    """Minimal stand-in for a MediaPipe NormalizedLandmark."""
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


def make_u_hand():
    """An upright right hand making the ASL 'U': index + middle extended and
    together, ring + pinky curled, thumb tucked to the side (not touching).
    Coordinates are normalized [0,1], y grows downward (image convention)."""
    return [
        LM(0.50, 0.90),  # 0 wrist
        LM(0.42, 0.80),  # 1 thumb cmc
        LM(0.38, 0.72),  # 2 thumb mcp
        LM(0.36, 0.66),  # 3 thumb ip
        LM(0.36, 0.60),  # 4 thumb tip (tucked, away from index base)
        LM(0.45, 0.60),  # 5 index mcp
        LM(0.44, 0.45),  # 6 index pip
        LM(0.43, 0.35),  # 7 index dip
        LM(0.43, 0.25),  # 8 index tip
        LM(0.52, 0.60),  # 9 middle mcp
        LM(0.53, 0.45),  # 10 middle pip
        LM(0.54, 0.35),  # 11 middle dip
        LM(0.54, 0.25),  # 12 middle tip
        LM(0.58, 0.62),  # 13 ring mcp
        LM(0.58, 0.55),  # 14 ring pip
        LM(0.575, 0.60), # 15 ring dip (curled back down)
        LM(0.57, 0.65),  # 16 ring tip (curled, near wrist)
        LM(0.63, 0.64),  # 17 pinky mcp
        LM(0.63, 0.58),  # 18 pinky pip
        LM(0.625, 0.62), # 19 pinky dip
        LM(0.62, 0.66),  # 20 pinky tip (curled)
    ]


def test_mcp_midpoint_is_between_index_and_middle_mcp():
    hand = make_u_hand()
    mx, my = detect.mcp_midpoint(hand)
    assert mx == (0.45 + 0.52) / 2
    assert my == (0.60 + 0.60) / 2


def test_hand_scale_is_wrist_to_mcp_midpoint_distance():
    hand = make_u_hand()
    mx, my = detect.mcp_midpoint(hand)
    expected = math.hypot(mx - 0.50, my - 0.90)
    assert detect.hand_scale(hand) == expected


def test_hand_axis_points_from_wrist_toward_fingers_and_is_unit_length():
    hand = make_u_hand()
    ax, ay = detect.hand_axis(hand)
    assert math.isclose(math.hypot(ax, ay), 1.0, rel_tol=1e-9)
    # Fingers are above the wrist (smaller y), so the axis points up (ay < 0).
    assert ay < 0
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python -m pytest tests/test_handmouse_detect.py -q`
Expected: FAIL with `AttributeError: module 'handvol.handmouse.detect' has no attribute 'mcp_midpoint'`.

- [ ] **Step 4: Implement the geometry primitives**

Create `handvol/handmouse/detect.py`:

```python
import math

# MediaPipe hand landmark indices.
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_TIP = 13, 16
PINKY_MCP, PINKY_TIP = 17, 20


def mcp_midpoint(landmarks):
    """(x, y) midpoint of the index and middle MCP knuckles."""
    a = landmarks[INDEX_MCP]
    b = landmarks[MIDDLE_MCP]
    return ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)


def hand_scale(landmarks):
    """Distance from the wrist to the MCP midpoint. Used to normalize all
    other distances so detection is invariant to how close the hand is."""
    mx, my = mcp_midpoint(landmarks)
    w = landmarks[WRIST]
    return math.hypot(mx - w.x, my - w.y)


def hand_axis(landmarks):
    """Unit vector pointing from the wrist toward the MCP midpoint — the
    direction the hand 'points'. Rotation-invariant basis for projection."""
    mx, my = mcp_midpoint(landmarks)
    w = landmarks[WRIST]
    dx, dy = mx - w.x, my - w.y
    length = math.hypot(dx, dy)
    if length == 0:
        return (0.0, -1.0)
    return (dx / length, dy / length)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_handmouse_detect.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add handvol/handmouse/__init__.py handvol/handmouse/detect.py tests/test_handmouse_detect.py
git commit -m "feat(handmouse): package skeleton and hand geometry primitives"
```

---

## Task 2: Projected cursor point (axis projection, method A)

**Files:**
- Modify: `handvol/handmouse/detect.py`
- Test: `tests/test_handmouse_detect.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_handmouse_detect.py`:

```python
def test_projected_point_lands_ahead_of_mcp_toward_fingers():
    hand = make_u_hand()
    mx, my = detect.mcp_midpoint(hand)
    px, py = detect.projected_point(hand, k=1.0)
    # The projected point sits beyond the MCP midpoint in the finger direction
    # (upward => smaller y), i.e. nearer the fingertips.
    assert py < my
    # It stays roughly under the fingers horizontally.
    assert abs(px - mx) < 0.1


def test_projected_point_is_stable_when_a_fingertip_bends():
    straight = make_u_hand()
    bent = make_u_hand()
    # Simulate a left-click: curl the index tip down toward the palm.
    bent[detect.INDEX_TIP] = LM(0.45, 0.55)
    bent[detect.INDEX_DIP] = LM(0.45, 0.58)
    p_straight = detect.projected_point(straight, k=1.0)
    p_bent = detect.projected_point(bent, k=1.0)
    # Cursor barely moves because it is built from wrist + knuckles, not tips.
    assert math.hypot(p_bent[0] - p_straight[0], p_bent[1] - p_straight[1]) < 0.01
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_handmouse_detect.py -k projected -q`
Expected: FAIL with `AttributeError: ... has no attribute 'projected_point'`.

- [ ] **Step 3: Implement `projected_point`**

Append to `handvol/handmouse/detect.py`:

```python
def projected_point(landmarks, k=1.0):
    """Cursor point in normalized frame coords. Starts at the MCP midpoint and
    projects forward along the hand axis by k * hand_scale, so it sits up near
    the fingertips while being computed only from the wrist and knuckles. This
    keeps it steady when a fingertip curls to click."""
    mx, my = mcp_midpoint(landmarks)
    ax, ay = hand_axis(landmarks)
    scale = hand_scale(landmarks)
    return (mx + ax * k * scale, my + ay * k * scale)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_handmouse_detect.py -k projected -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/detect.py tests/test_handmouse_detect.py
git commit -m "feat(handmouse): axis-projected cursor point stable under finger bends"
```

---

## Task 3: PIP joint angle (click bend signal)

**Files:**
- Modify: `handvol/handmouse/detect.py`
- Test: `tests/test_handmouse_detect.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_handmouse_detect.py`:

```python
def test_pip_angle_straight_finger_near_180():
    hand = make_u_hand()
    angle = detect.pip_angle(hand, detect.INDEX_MCP, detect.INDEX_PIP, detect.INDEX_TIP)
    assert angle > 150


def test_pip_angle_bent_finger_is_small():
    hand = make_u_hand()
    # Curl the index: tip folds back toward the MCP.
    hand[detect.INDEX_DIP] = LM(0.45, 0.55)
    hand[detect.INDEX_TIP] = LM(0.47, 0.62)
    angle = detect.pip_angle(hand, detect.INDEX_MCP, detect.INDEX_PIP, detect.INDEX_TIP)
    assert angle < 110
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_handmouse_detect.py -k pip_angle -q`
Expected: FAIL with `AttributeError: ... has no attribute 'pip_angle'`.

- [ ] **Step 3: Implement `pip_angle`**

Append to `handvol/handmouse/detect.py`:

```python
def pip_angle(landmarks, mcp_idx, pip_idx, tip_idx):
    """Angle in degrees at the PIP joint, between the bones MCP->PIP and
    PIP->TIP. A straight finger is near 180 degrees; a bent finger drops well
    below. Angle-based, so it reads the same across hand tilt and hand size."""
    mcp = landmarks[mcp_idx]
    pip = landmarks[pip_idx]
    tip = landmarks[tip_idx]
    v1x, v1y = mcp.x - pip.x, mcp.y - pip.y
    v2x, v2y = tip.x - pip.x, tip.y - pip.y
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 == 0 or n2 == 0:
        return 180.0
    cos = (v1x * v2x + v1y * v2y) / (n1 * n2)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_handmouse_detect.py -k pip_angle -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/detect.py tests/test_handmouse_detect.py
git commit -m "feat(handmouse): PIP joint angle for tilt-invariant bend detection"
```

---

## Task 4: Palm-facing check and U-sign detection

**Files:**
- Modify: `handvol/handmouse/detect.py`
- Test: `tests/test_handmouse_detect.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_handmouse_detect.py`:

```python
def test_hand_normal_z_flips_sign_when_hand_is_mirrored():
    hand = make_u_hand()
    z = detect.hand_normal_z(hand)
    mirrored = [LM(1.0 - lm.x, lm.y, lm.z) for lm in hand]
    zm = detect.hand_normal_z(mirrored)
    assert (z > 0) != (zm > 0)


def test_detect_u_sign_true_for_canonical_u():
    hand = make_u_hand()
    # In this mirrored selfie pipeline MediaPipe labels the user's right hand
    # as "Left" (same convention capture.py's side-thumb detector relies on).
    assert detect.detect_u_sign(hand, "Left") is True


def test_detect_u_sign_false_when_fingers_spread_like_victory():
    hand = make_u_hand()
    # Spread the tips far apart -> Victory, not U.
    hand[detect.INDEX_TIP] = LM(0.30, 0.25)
    hand[detect.MIDDLE_TIP] = LM(0.70, 0.25)
    assert detect.detect_u_sign(hand, "Left") is False


def test_detect_u_sign_false_when_ring_extended():
    hand = make_u_hand()
    hand[detect.RING_TIP] = LM(0.60, 0.25)  # ring now extended
    assert detect.detect_u_sign(hand, "Left") is False


def test_detect_u_sign_false_for_wrong_handedness():
    hand = make_u_hand()
    # Same coords but the opposite handedness => palm-facing check rejects.
    assert detect.detect_u_sign(hand, "Right") is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_handmouse_detect.py -k "normal or u_sign" -q`
Expected: FAIL with `AttributeError: ... has no attribute 'hand_normal_z'`.

- [ ] **Step 3: Implement `hand_normal_z`, `palm_facing`, `_extended`, `_curled`, `detect_u_sign`**

Append to `handvol/handmouse/detect.py`:

```python
EXTEND_RATIO = 1.6   # tip must be this much farther from wrist than its MCP
CURL_RATIO = 1.25    # curled tip stays within this * its MCP distance
TOGETHER_RATIO = 2.0  # index/middle tips closer than this * their MCP gap

# Sign of hand_normal_z that means "palm toward camera". The canonical
# make_u_hand (a user's right hand, MediaPipe label "Left") yields a positive
# normal, so "Left" expects > 0. Flip these if real-world testing shows the
# pose only registers when the back of the hand faces the camera.
PALM_SIGN = {"Left": 1.0, "Right": -1.0}


def _dist_to_wrist(landmarks, idx):
    w = landmarks[WRIST]
    p = landmarks[idx]
    return math.hypot(p.x - w.x, p.y - w.y)


def _extended(landmarks, mcp_idx, tip_idx):
    return _dist_to_wrist(landmarks, tip_idx) > _dist_to_wrist(landmarks, mcp_idx) * EXTEND_RATIO


def _curled(landmarks, mcp_idx, tip_idx):
    return _dist_to_wrist(landmarks, tip_idx) < _dist_to_wrist(landmarks, mcp_idx) * CURL_RATIO


def hand_normal_z(landmarks):
    """Z component of the hand-plane normal, as a 2D cross product of
    wrist->index_MCP and wrist->pinky_MCP. Its sign flips between palm-facing
    and back-facing for a given hand."""
    w = landmarks[WRIST]
    i = landmarks[INDEX_MCP]
    p = landmarks[PINKY_MCP]
    v1x, v1y = i.x - w.x, i.y - w.y
    v2x, v2y = p.x - w.x, p.y - w.y
    return v1x * v2y - v1y * v2x


def palm_facing(landmarks, handedness):
    """True when the palm faces the camera for the given MediaPipe handedness."""
    sign = PALM_SIGN.get(handedness)
    if sign is None:
        return False
    return hand_normal_z(landmarks) * sign > 0


def detect_u_sign(landmarks, handedness):
    """Strict U pose used to ENTER pointer mode: index + middle extended and
    held together, ring + pinky curled, palm facing the camera."""
    if not landmarks or len(landmarks) < 21:
        return False
    if not palm_facing(landmarks, handedness):
        return False
    if not (_extended(landmarks, INDEX_MCP, INDEX_TIP)
            and _extended(landmarks, MIDDLE_MCP, MIDDLE_TIP)):
        return False
    if not (_curled(landmarks, RING_MCP, RING_TIP)
            and _curled(landmarks, PINKY_MCP, PINKY_TIP)):
        return False
    tip_gap = math.hypot(landmarks[INDEX_TIP].x - landmarks[MIDDLE_TIP].x,
                         landmarks[INDEX_TIP].y - landmarks[MIDDLE_TIP].y)
    mcp_gap = math.hypot(landmarks[INDEX_MCP].x - landmarks[MIDDLE_MCP].x,
                         landmarks[INDEX_MCP].y - landmarks[MIDDLE_MCP].y)
    if mcp_gap == 0 or tip_gap > mcp_gap * TOGETHER_RATIO:
        return False
    return True
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_handmouse_detect.py -k "normal or u_sign" -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/detect.py tests/test_handmouse_detect.py
git commit -m "feat(handmouse): strict U-sign detection with palm-facing gate"
```

---

## Task 5: Thumb-touch scroll engagement

**Files:**
- Modify: `handvol/handmouse/detect.py`
- Test: `tests/test_handmouse_detect.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_handmouse_detect.py`:

```python
def test_thumb_touch_false_when_thumb_tucked():
    hand = make_u_hand()
    assert detect.thumb_touch(hand) is False


def test_thumb_touch_true_when_thumb_pad_near_index_base():
    hand = make_u_hand()
    # Move the thumb tip onto the index MCP (knuckle/base), index still straight.
    hand[detect.THUMB_TIP] = LM(0.45, 0.60)
    assert detect.thumb_touch(hand) is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_handmouse_detect.py -k thumb_touch -q`
Expected: FAIL with `AttributeError: ... has no attribute 'thumb_touch'`.

- [ ] **Step 3: Implement `thumb_touch`**

Append to `handvol/handmouse/detect.py`:

```python
THUMB_TOUCH_RATIO = 0.2  # thumb tip within this * hand_scale of the index base


def thumb_touch(landmarks):
    """True when the thumb pad rests on the side/base of the index finger
    (near its MCP). Engages scroll while index + middle stay straight, so it
    never collides with the bend-based clicks."""
    if not landmarks or len(landmarks) < 21:
        return False
    t = landmarks[THUMB_TIP]
    base = landmarks[INDEX_MCP]
    d = math.hypot(t.x - base.x, t.y - base.y)
    return d < hand_scale(landmarks) * THUMB_TOUCH_RATIO
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_handmouse_detect.py -k thumb_touch -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/detect.py tests/test_handmouse_detect.py
git commit -m "feat(handmouse): thumb-touch detection for scroll engagement"
```

---

## Task 6: One-Euro filter

**Files:**
- Create: `handvol/handmouse/pointer.py`
- Create: `tests/test_pointer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pointer.py`:

```python
from handvol.handmouse.pointer import OneEuroFilter


def test_constant_input_returns_constant():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0, d_cutoff=1.0)
    t = 0.0
    out = []
    for _ in range(10):
        out.append(f(0.5, t))
        t += 1 / 30
    assert all(abs(v - 0.5) < 1e-9 for v in out)


def test_output_moves_toward_a_step_input_but_lags():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0, d_cutoff=1.0)
    t = 0.0
    f(0.0, t)            # establish baseline at 0
    t += 1 / 30
    first = f(1.0, t)    # step to 1.0
    assert 0.0 < first < 1.0          # lagged, not instant
    prev = first
    for _ in range(30):
        t += 1 / 30
        cur = f(1.0, t)
        assert cur >= prev - 1e-9     # monotonically approaches the target
        prev = cur
    assert prev > 0.9                 # converges close to 1.0


def test_reset_restores_initial_behavior():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0, d_cutoff=1.0)
    f(0.0, 0.0)
    f(1.0, 1 / 30)
    f.reset()
    assert f(0.7, 0.0) == 0.7         # first call after reset returns input
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_pointer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'handvol.handmouse.pointer'`.

- [ ] **Step 3: Implement `OneEuroFilter`**

Create `handvol/handmouse/pointer.py`:

```python
import math


class _LowPass:
    def __init__(self):
        self.y = None

    def __call__(self, x, alpha):
        if self.y is None:
            self.y = x
        else:
            self.y = alpha * x + (1 - alpha) * self.y
        return self.y

    def reset(self):
        self.y = None


class OneEuroFilter:
    """One-Euro filter: smooths jitter when the value is steady and cuts lag
    when it moves fast. Better than a fixed EMA for a moving cursor."""

    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = _LowPass()
        self._dx = _LowPass()
        self._t_prev = None
        self._x_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self._t_prev is None:
            self._t_prev = t
            self._x_prev = x
            self._x(x, 1.0)
            self._dx(0.0, 1.0)
            return x
        dt = t - self._t_prev
        if dt <= 0:
            dt = 1e-3
        dx = (x - self._x_prev) / dt
        edx = self._dx(dx, self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        y = self._x(x, self._alpha(cutoff, dt))
        self._t_prev = t
        self._x_prev = x
        return y

    def reset(self):
        self._x.reset()
        self._dx.reset()
        self._t_prev = None
        self._x_prev = None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_pointer.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/pointer.py tests/test_pointer.py
git commit -m "feat(handmouse): One-Euro filter for cursor smoothing"
```

---

## Task 7: Absolute mapper (active region + snap)

**Files:**
- Modify: `handvol/handmouse/pointer.py`
- Test: `tests/test_pointer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pointer.py`:

```python
from handvol.handmouse.pointer import AbsoluteMapper


def test_absolute_center_of_active_region_maps_to_screen_center():
    m = AbsoluteMapper(screen_w=1920, screen_h=1080, active=0.65)
    x, y = m.map((0.5, 0.5), just_acquired=True)
    assert x == 960
    assert y == 540


def test_absolute_active_region_edge_maps_to_screen_edge():
    m = AbsoluteMapper(screen_w=1920, screen_h=1080, active=0.65)
    lo = (1 - 0.65) / 2  # 0.175
    x0, y0 = m.map((lo, lo), just_acquired=False)
    x1, y1 = m.map((1 - lo, 1 - lo), just_acquired=False)
    assert (x0, y0) == (0, 0)
    assert (x1, y1) == (1920, 1080)


def test_absolute_clamps_outside_active_region():
    m = AbsoluteMapper(screen_w=1920, screen_h=1080, active=0.65)
    x, y = m.map((0.0, 0.0), just_acquired=False)
    assert (x, y) == (0, 0)
    x, y = m.map((1.0, 1.0), just_acquired=False)
    assert (x, y) == (1920, 1080)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_pointer.py -k absolute -q`
Expected: FAIL with `ImportError: cannot import name 'AbsoluteMapper'`.

- [ ] **Step 3: Implement `AbsoluteMapper`**

Append to `handvol/handmouse/pointer.py`:

```python
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class AbsoluteMapper:
    """Maps the center `active` fraction of the camera frame to the full target
    monitor. Reaching a screen edge needs the hand only near the middle of the
    frame, so the whole hand stays visible. Position is absolute, so it snaps to
    the hand inherently; `just_acquired` is accepted for interface symmetry."""

    def __init__(self, screen_w, screen_h, active=0.65):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.active = active

    def map(self, point, just_acquired):
        lo = (1 - self.active) / 2
        span = 1 - 2 * lo
        nx = _clamp((point[0] - lo) / span, 0.0, 1.0)
        ny = _clamp((point[1] - lo) / span, 0.0, 1.0)
        return (int(round(nx * self.screen_w)), int(round(ny * self.screen_h)))

    def reset(self):
        pass
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_pointer.py -k absolute -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/pointer.py tests/test_pointer.py
git commit -m "feat(handmouse): absolute mapper with active region and clamping"
```

---

## Task 8: Relative mapper (clutching)

**Files:**
- Modify: `handvol/handmouse/pointer.py`
- Test: `tests/test_pointer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pointer.py`:

```python
from handvol.handmouse.pointer import RelativeMapper


def test_relative_first_map_after_acquire_does_not_jump():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=1.0)
    m.set_cursor(900, 500)
    x, y = m.map((0.2, 0.2), just_acquired=True)
    assert (x, y) == (900, 500)  # establishes reference, no move


def test_relative_accumulates_deltas():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=1.0)
    m.set_cursor(900, 500)
    m.map((0.5, 0.5), just_acquired=True)        # reference
    x, y = m.map((0.6, 0.5), just_acquired=False)  # +0.1 of width
    assert x == 900 + int(round(0.1 * 1920))
    assert y == 500


def test_relative_clutch_resets_reference_on_reacquire():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=1.0)
    m.set_cursor(900, 500)
    m.map((0.5, 0.5), just_acquired=True)
    m.map((0.7, 0.5), just_acquired=False)       # cursor moves right
    moved_x, moved_y = m.map((0.2, 0.2), just_acquired=True)  # re-acquire elsewhere
    assert (moved_x, moved_y) == (m.cursor_x, m.cursor_y)  # no jump on reacquire


def test_relative_clamps_to_screen_bounds():
    m = RelativeMapper(screen_w=1920, screen_h=1080, gain=10.0)
    m.set_cursor(0, 0)
    m.map((0.5, 0.5), just_acquired=True)
    x, y = m.map((1.0, 1.0), just_acquired=False)
    assert (x, y) == (1920, 1080)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_pointer.py -k relative -q`
Expected: FAIL with `ImportError: cannot import name 'RelativeMapper'`.

- [ ] **Step 3: Implement `RelativeMapper`**

Append to `handvol/handmouse/pointer.py`:

```python
class RelativeMapper:
    """Trackpad-style mapping: adds gain-scaled hand deltas to the cursor.
    On re-acquisition it resets the reference point so the cursor resumes from
    where it sits instead of jumping — the clutch."""

    def __init__(self, screen_w, screen_h, gain=2.0):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.gain = gain
        self.cursor_x = screen_w // 2
        self.cursor_y = screen_h // 2
        self._last = None

    def set_cursor(self, x, y):
        self.cursor_x = int(_clamp(x, 0, self.screen_w))
        self.cursor_y = int(_clamp(y, 0, self.screen_h))

    def map(self, point, just_acquired):
        if just_acquired or self._last is None:
            self._last = point
            return (self.cursor_x, self.cursor_y)
        dx = (point[0] - self._last[0]) * self.gain * self.screen_w
        dy = (point[1] - self._last[1]) * self.gain * self.screen_h
        self.cursor_x = int(round(_clamp(self.cursor_x + dx, 0, self.screen_w)))
        self.cursor_y = int(round(_clamp(self.cursor_y + dy, 0, self.screen_h)))
        self._last = point
        return (self.cursor_x, self.cursor_y)

    def reset(self):
        self._last = None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_pointer.py -k relative -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/pointer.py tests/test_pointer.py
git commit -m "feat(handmouse): relative mapper with clutching"
```

---

## Task 9: Bend trigger (Schmitt)

**Files:**
- Modify: `handvol/handmouse/pointer.py`
- Test: `tests/test_pointer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pointer.py`:

```python
from handvol.handmouse.pointer import BendTrigger


def test_bend_trigger_engages_below_engage_and_holds_through_hysteresis():
    t = BendTrigger(engage_deg=100, release_deg=130)
    assert t.update(170) is False    # straight
    assert t.update(95) is True      # crosses engage -> bent
    assert t.update(120) is True     # in the hysteresis band -> still bent
    assert t.update(135) is False    # crosses release -> straight again


def test_bend_trigger_no_chatter_in_band():
    t = BendTrigger(engage_deg=100, release_deg=130)
    t.update(170)
    states = [t.update(a) for a in (105, 110, 115, 120, 125)]
    assert states == [False, False, False, False, False]  # never engaged in band
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_pointer.py -k bend -q`
Expected: FAIL with `ImportError: cannot import name 'BendTrigger'`.

- [ ] **Step 3: Implement `BendTrigger`**

Append to `handvol/handmouse/pointer.py`:

```python
class BendTrigger:
    """Schmitt trigger over a finger's PIP angle. Becomes 'bent' only after the
    angle drops below engage_deg, and 'straight' again only after it rises above
    release_deg. The gap (engage < release) stops a single bend from chattering
    into multiple click events."""

    def __init__(self, engage_deg=100.0, release_deg=130.0):
        self.engage_deg = engage_deg
        self.release_deg = release_deg
        self.bent = False

    def update(self, angle_deg):
        if self.bent:
            if angle_deg > self.release_deg:
                self.bent = False
        else:
            if angle_deg < self.engage_deg:
                self.bent = True
        return self.bent

    def reset(self):
        self.bent = False
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_pointer.py -k bend -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/pointer.py tests/test_pointer.py
git commit -m "feat(handmouse): Schmitt bend trigger for chatter-free clicks"
```

---

## Task 10: HandPointer orchestrator

**Files:**
- Modify: `handvol/handmouse/pointer.py`
- Test: `tests/test_pointer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pointer.py`:

```python
from handvol.handmouse.pointer import HandPointer, PointerAction
from tests.test_handmouse_detect import make_u_hand, LM


def _mapper_stub():
    return AbsoluteMapper(screen_w=1000, screen_h=1000, active=0.65)


def test_process_returns_move_with_no_click_for_plain_u():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    action = hp.process(make_u_hand(), t=0.0)
    assert isinstance(action, PointerAction)
    assert action.move is not None
    assert action.left_edge is None
    assert action.right_edge is None
    assert action.scroll == 0


def test_process_emits_left_down_then_up_on_index_bend_cycle():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    hp.process(make_u_hand(), t=0.0)             # straight baseline
    bent = make_u_hand()
    bent[7] = LM(0.45, 0.55)                       # index dip
    bent[8] = LM(0.47, 0.62)                       # index tip folded
    a_down = hp.process(bent, t=0.033)
    assert a_down.left_edge == "down"
    a_hold = hp.process(bent, t=0.066)
    assert a_hold.left_edge is None               # held, no repeat (drag)
    a_up = hp.process(make_u_hand(), t=0.099)     # straighten
    assert a_up.left_edge == "up"


def test_process_scrolls_and_suppresses_clicks_while_thumb_touches():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    touch = make_u_hand()
    touch[4] = LM(0.45, 0.60)                      # thumb on index base
    hp.process(touch, t=0.0)                        # establish scroll anchor
    moved = make_u_hand()
    moved[4] = LM(0.45, 0.50)                      # thumb still touching, hand up
    # shift the whole hand up so projected point rises
    moved = [LM(p.x, p.y - 0.1, p.z) for p in moved]
    moved[4] = LM(0.45, 0.40)
    action = hp.process(moved, t=0.033)
    assert action.move is None                      # no cursor move while scrolling
    assert action.left_edge is None
    assert action.scroll != 0


def test_release_sends_up_for_held_button():
    hp = HandPointer(_mapper_stub(), k=1.0)
    hp.acquire()
    hp.process(make_u_hand(), t=0.0)
    bent = make_u_hand()
    bent[7] = LM(0.45, 0.55)
    bent[8] = LM(0.47, 0.62)
    hp.process(bent, t=0.033)                       # left down (held)
    ups = hp.release()
    assert ("left", "up") in ups
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_pointer.py -k "process or release" -q`
Expected: FAIL with `ImportError: cannot import name 'HandPointer'`.

- [ ] **Step 3: Implement `PointerAction` and `HandPointer`**

Append to `handvol/handmouse/pointer.py`:

```python
from collections import namedtuple

from handvol.handmouse import detect

PointerAction = namedtuple("PointerAction", "move left_edge right_edge scroll")

SCROLL_GAIN = 800.0  # wheel ticks per unit of normalized vertical travel


class HandPointer:
    """Turns per-frame landmarks into a PointerAction: where to move, click
    edges (down/up transitions), and scroll ticks. Holds smoothing filters, the
    active screen mapper, bend triggers, and scroll state. Clicks are derived
    from PIP geometry, never from gesture labels."""

    def __init__(self, mapper, k=1.0, scroll_invert=False):
        self.mapper = mapper
        self.k = k
        self.scroll_invert = scroll_invert
        self._fx = OneEuroFilter(min_cutoff=1.0, beta=0.7, d_cutoff=1.0)
        self._fy = OneEuroFilter(min_cutoff=1.0, beta=0.7, d_cutoff=1.0)
        self._index = BendTrigger()
        self._middle = BendTrigger()
        self._just_acquired = True
        self._scroll_anchor_y = None
        self._left_down = False
        self._right_down = False

    def acquire(self):
        """Call when (re)entering pointer mode: reset smoothing, clutch, and
        click state so a fresh pose does not inherit stale deltas."""
        self._fx.reset()
        self._fy.reset()
        self._index.reset()
        self._middle.reset()
        self.mapper.reset()
        self._just_acquired = True
        self._scroll_anchor_y = None

    def process(self, landmarks, t):
        px, py = detect.projected_point(landmarks, k=self.k)
        sx = self._fx(px, t)
        sy = self._fy(py, t)

        if detect.thumb_touch(landmarks):
            if self._scroll_anchor_y is None:
                self._scroll_anchor_y = sy
                return PointerAction(None, None, None, 0)
            delta = self._scroll_anchor_y - sy  # hand up (smaller y) -> positive
            self._scroll_anchor_y = sy
            ticks = int(round(delta * SCROLL_GAIN))
            if self.scroll_invert:
                ticks = -ticks
            return PointerAction(None, None, None, ticks)

        self._scroll_anchor_y = None

        index_angle = detect.pip_angle(
            landmarks, detect.INDEX_MCP, detect.INDEX_PIP, detect.INDEX_TIP)
        middle_angle = detect.pip_angle(
            landmarks, detect.MIDDLE_MCP, detect.MIDDLE_PIP, detect.MIDDLE_TIP)
        left_edge = self._edge(self._index, index_angle, "left")
        right_edge = self._edge(self._middle, middle_angle, "right")

        move = self.mapper.map((sx, sy), self._just_acquired)
        self._just_acquired = False
        return PointerAction(move, left_edge, right_edge, 0)

    def _edge(self, trigger, angle, button):
        was = trigger.bent
        now = trigger.update(angle)
        if now and not was:
            if button == "left":
                self._left_down = True
            else:
                self._right_down = True
            return "down"
        if was and not now:
            if button == "left":
                self._left_down = False
            else:
                self._right_down = False
            return "up"
        return None

    def release(self):
        """On pointer-mode exit, return up-edges for any buttons still held so a
        click cannot get stuck down."""
        ups = []
        if self._left_down:
            ups.append(("left", "up"))
            self._left_down = False
        if self._right_down:
            ups.append(("right", "up"))
            self._right_down = False
        return ups
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_pointer.py -q`
Expected: PASS (all pointer tests pass).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/pointer.py tests/test_pointer.py
git commit -m "feat(handmouse): HandPointer orchestrator producing pointer actions"
```

---

## Task 11: Mouse OS injection layer

**Files:**
- Create: `handvol/handmouse/mouse.py`
- Create: `tests/test_mouse.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_mouse.py`:

```python
from handvol.handmouse.mouse import Monitor, VirtualScreen, to_absolute, Mouse


def test_to_absolute_maps_monitor_corner_to_zero():
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=0, top=0, width=1920, height=1080)
    ax, ay = to_absolute(0, 0, mon, virt)
    assert (ax, ay) == (0, 0)


def test_to_absolute_maps_monitor_far_corner_to_65535():
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=0, top=0, width=1920, height=1080)
    ax, ay = to_absolute(1920, 1080, mon, virt)
    assert ax == 65535
    assert ay == 65535


def test_to_absolute_accounts_for_secondary_monitor_offset():
    # Primary on the right of a second monitor: virtual origin is negative.
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=-1920, top=0, width=3840, height=1080)
    ax, _ = to_absolute(0, 0, mon, virt)
    # Local (0,0) is at virtual x=0, which is halfway across a 3840 desktop.
    assert ax == round(1920 * 65535 / 3839)


def test_mouse_sink_records_move_and_click_sequence():
    mon = Monitor(left=0, top=0, width=1920, height=1080)
    virt = VirtualScreen(left=0, top=0, width=1920, height=1080)
    sink = []
    m = Mouse(mon, virt, sink=sink)
    m.move_to(960, 540)
    m.left_down()
    m.left_up()
    m.scroll(3)
    assert sink[0][0] == "move"
    assert sink[1] == ("left_down",)
    assert sink[2] == ("left_up",)
    assert sink[3] == ("scroll", 3)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_mouse.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'handvol.handmouse.mouse'`.

- [ ] **Step 3: Implement `mouse.py`**

Create `handvol/handmouse/mouse.py`:

```python
import ctypes
from collections import namedtuple

Monitor = namedtuple("Monitor", "left top width height")
VirtualScreen = namedtuple("VirtualScreen", "left top width height")

# GetSystemMetrics indices.
_SM_CXSCREEN = 0
_SM_CYSCREEN = 1
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

# SendInput constants.
_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_WHEEL = 0x0800
_WHEEL_DELTA = 120


def to_absolute(x_local, y_local, monitor, virt):
    """Convert a monitor-local pixel position to the 0..65535 absolute
    coordinate space SendInput uses across the whole virtual desktop."""
    vx = monitor.left + x_local - virt.left
    vy = monitor.top + y_local - virt.top
    ax = round(vx * 65535 / (virt.width - 1))
    ay = round(vy * 65535 / (virt.height - 1))
    return (max(0, min(65535, ax)), max(0, min(65535, ay)))


def get_primary_monitor():
    u = ctypes.windll.user32
    return Monitor(0, 0, u.GetSystemMetrics(_SM_CXSCREEN),
                   u.GetSystemMetrics(_SM_CYSCREEN))


def get_virtual_screen():
    u = ctypes.windll.user32
    return VirtualScreen(
        u.GetSystemMetrics(_SM_XVIRTUALSCREEN),
        u.GetSystemMetrics(_SM_YVIRTUALSCREEN),
        u.GetSystemMetrics(_SM_CXVIRTUALSCREEN),
        u.GetSystemMetrics(_SM_CYVIRTUALSCREEN),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


class Mouse:
    """OS cursor injection via SendInput. Pass a list as `sink` to capture the
    intended calls in tests instead of moving the real cursor."""

    def __init__(self, monitor, virt, sink=None):
        self.monitor = monitor
        self.virt = virt
        self.sink = sink

    def _send(self, flags, dx=0, dy=0, data=0):
        if self.sink is not None:
            return
        mi = _MOUSEINPUT(dx, dy, data, flags, 0, None)
        inp = _INPUT(_INPUT_MOUSE, _INPUT._U(mi))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def move_to(self, x_local, y_local):
        ax, ay = to_absolute(x_local, y_local, self.monitor, self.virt)
        if self.sink is not None:
            self.sink.append(("move", ax, ay))
            return
        self._send(_MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE
                   | _MOUSEEVENTF_VIRTUALDESK, ax, ay)

    def left_down(self):
        if self.sink is not None:
            self.sink.append(("left_down",))
            return
        self._send(_MOUSEEVENTF_LEFTDOWN)

    def left_up(self):
        if self.sink is not None:
            self.sink.append(("left_up",))
            return
        self._send(_MOUSEEVENTF_LEFTUP)

    def right_down(self):
        if self.sink is not None:
            self.sink.append(("right_down",))
            return
        self._send(_MOUSEEVENTF_RIGHTDOWN)

    def right_up(self):
        if self.sink is not None:
            self.sink.append(("right_up",))
            return
        self._send(_MOUSEEVENTF_RIGHTUP)

    def scroll(self, ticks):
        if self.sink is not None:
            self.sink.append(("scroll", ticks))
            return
        self._send(_MOUSEEVENTF_WHEEL, data=ticks * _WHEEL_DELTA)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_mouse.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add handvol/handmouse/mouse.py tests/test_mouse.py
git commit -m "feat(handmouse): SendInput mouse layer with testable sink"
```

---

## Task 12: State machine POINTER mode

**Files:**
- Modify: `handvol/state.py`
- Test: `tests/test_pointer_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pointer_state.py`:

```python
from handvol.state import (
    GestureStateMachine, State, Event,
    U_SIGN, POINTER_ENTER_FRAMES, POINTER_EXIT_FRAMES,
)
from handvol.state import POINTING_UP, MIDDLE_FINGER


def test_enters_pointer_after_enter_frames_of_u_sign():
    sm = GestureStateMachine()
    events = [sm.step(U_SIGN) for _ in range(POINTER_ENTER_FRAMES)]
    assert sm.state is State.POINTER
    assert events[-1] is Event.ENTER_POINTER
    assert all(e is Event.NONE for e in events[:-1])


def test_pointer_update_each_frame_while_held():
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    assert sm.step(U_SIGN) is Event.POINTER_UPDATE


def test_click_poses_keep_pointer_alive():
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    # Bending a finger to click looks like Pointing_Up or middle_finger.
    assert sm.step(POINTING_UP) is Event.POINTER_UPDATE
    assert sm.step(MIDDLE_FINGER) is Event.POINTER_UPDATE
    assert sm.state is State.POINTER


def test_exits_pointer_after_exit_frames_of_non_pose():
    sm = GestureStateMachine()
    for _ in range(POINTER_ENTER_FRAMES):
        sm.step(U_SIGN)
    events = [sm.step("None") for _ in range(POINTER_EXIT_FRAMES)]
    assert events[-1] is Event.EXIT_POINTER
    assert sm.state is State.IDLE


def test_pointing_up_in_idle_still_toggles_preview_not_pointer():
    sm = GestureStateMachine()
    from handvol.state import TOGGLE_FRAMES
    events = [sm.step(POINTING_UP) for _ in range(TOGGLE_FRAMES)]
    assert events[-1] is Event.TOGGLE_PREVIEW
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_pointer_state.py -q`
Expected: FAIL with `ImportError: cannot import name 'U_SIGN'`.

- [ ] **Step 3: Implement POINTER state, events, and constants**

In `handvol/state.py`, add to the `State` enum (after `IDLE_COOLDOWN`):

```python
    POINTER = "POINTER"
```

Add to the `Event` enum (after `CONTROL_TAB`):

```python
    ENTER_POINTER = "enter_pointer"
    POINTER_UPDATE = "pointer_update"
    EXIT_POINTER = "exit_pointer"
```

Add constants near the other gesture-name constants:

```python
U_SIGN = "U_sign"
POINTER_ENTER_FRAMES = 5
POINTER_EXIT_FRAMES = 3
# Poses that keep POINTER alive: the U itself plus the two click poses it
# momentarily becomes when a finger bends (index bend -> middle alone looks like
# middle_finger; middle bend -> index alone looks like Pointing_Up).
POINTER_HOLD_POSES = (U_SIGN, POINTING_UP, MIDDLE_FINGER)
```

In `__init__` and `_reset_counters`, add the counter (alongside the others):

```python
        self._u_sign_count = 0
        self._pointer_exit_count = 0
```

In `_bump`, add (with the other per-gesture counters):

```python
        self._u_sign_count = self._u_sign_count + 1 if gesture == U_SIGN else 0
```

Add `U_SIGN` to the neutral-reset gesture tuple in `_bump` (the big `if is_skip or is_prev or gesture in (...)` block) so a U pose does not increment `_neutral_count`:

```python
            U_SIGN,
```

In `step`, inside the `if self.state is State.IDLE:` block, add this BEFORE the `_pointer_count` (Pointing_Up) check so the U sign wins over toggle-preview when both fingers are up:

```python
            if self._u_sign_count >= POINTER_ENTER_FRAMES:
                self.state = State.POINTER
                self._reset_counters()
                return Event.ENTER_POINTER
```

Add a new state block AFTER the `if self.state is State.SCRUB:` block and BEFORE the `# IDLE_COOLDOWN` block:

```python
        if self.state is State.POINTER:
            if gesture in POINTER_HOLD_POSES:
                self._pointer_exit_count = 0
                return Event.POINTER_UPDATE
            self._pointer_exit_count += 1
            if self._pointer_exit_count >= POINTER_EXIT_FRAMES:
                self.state = State.IDLE
                self._reset_counters()
                return Event.EXIT_POINTER
            return Event.NONE
```

Also add `self._pointer_exit_count = 0` to `_reset_counters`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_pointer_state.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS (all existing tests still green).

- [ ] **Step 6: Commit**

```bash
git add handvol/state.py tests/test_pointer_state.py
git commit -m "feat(state): POINTER mode sticky across click poses"
```

---

## Task 13: Capture integration (emit U_sign)

**Files:**
- Modify: `handvol/capture.py`
- Test: `tests/test_handmouse_detect.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_handmouse_detect.py`:

```python
from handvol import capture


def test_resolve_hand_labels_u_sign_before_victory():
    hand = make_u_hand()
    # MediaPipe would call a two-finger pose "Victory"; our U detector wins.
    name, score = capture._resolve_hand(hand, "Left", "Victory", 0.9)
    assert name == "U_sign"
    assert score == 1.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_handmouse_detect.py -k resolve_hand -q`
Expected: FAIL with `AssertionError` (name is "Victory", not "U_sign").

- [ ] **Step 3: Wire the detector into `_resolve_hand`**

In `handvol/capture.py`, add the import near the top (after the existing imports):

```python
from handvol.handmouse import detect as hm_detect
```

In `_resolve_hand`, add the U-sign check. Place it AFTER the `_detect_ok_sign` check and BEFORE `_detect_side_thumb`, so volume scrub keeps priority but the U beats Victory/Pointing_Up:

```python
    if hm_detect.detect_u_sign(landmarks, handedness):
        return "U_sign", 1.0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_handmouse_detect.py -k resolve_hand -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add handvol/capture.py tests/test_handmouse_detect.py
git commit -m "feat(capture): emit U_sign label ahead of Victory/Pointing_Up"
```

---

## Task 14: Overlay drawing for pointer mode

**Files:**
- Modify: `handvol/overlay.py`

No unit test: the overlay module draws onto OpenCV frames and has no existing tests, matching the codebase convention. Verify by eye during the manual smoke test in Task 16.

- [ ] **Step 1: Add the draw helpers**

Append to `handvol/overlay.py`:

```python
def draw_active_region(frame, active=0.65):
    """Dashed-looking rectangle marking the camera sub-region mapped to the
    screen in absolute pointer mode."""
    h, w = frame.shape[:2]
    lo = (1 - active) / 2
    x0, y0 = int(lo * w), int(lo * h)
    x1, y1 = int((1 - lo) * w), int((1 - lo) * h)
    cv2.rectangle(frame, (x0, y0), (x1, y1), CYAN, 1, cv2.LINE_AA)


def draw_pointer(frame, point_norm, left_bent=False, right_bent=False, scrolling=False):
    """Crosshair at the projected cursor point. Green normally, red while a
    button is held, yellow while scrolling."""
    if point_norm is None:
        return
    h, w = frame.shape[:2]
    cx, cy = int(point_norm[0] * w), int(point_norm[1] * h)
    color = YELLOW if scrolling else (RED if (left_bent or right_bent) else GREEN)
    cv2.circle(frame, (cx, cy), 9, color, 2, cv2.LINE_AA)
    cv2.line(frame, (cx - 14, cy), (cx + 14, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy - 14), (cx, cy + 14), color, 1, cv2.LINE_AA)
    label = "SCROLL" if scrolling else ("L" if left_bent else "") + ("R" if right_bent else "")
    if label:
        _put(frame, label, (cx + 16, cy - 16), color, 0.5, 1)
```

- [ ] **Step 2: Sanity-check the import surface**

Run: `python -c "from handvol.overlay import draw_active_region, draw_pointer; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add handvol/overlay.py
git commit -m "feat(overlay): active region and pointer crosshair drawing"
```

---

## Task 15: Dispatch wiring and CLI flags

**Files:**
- Modify: `handvol.pyw`

No unit test: `handvol.pyw` is the threaded entry point with camera and OS side effects and has no existing tests. Verify via the manual smoke test in Task 16.

- [ ] **Step 1: Add CLI flags**

In `handvol.pyw`, inside `parse_args`, add before `return p.parse_args()`:

```python
    p.add_argument("--pointer-mode", choices=["absolute", "relative"],
                   default="absolute",
                   help="Hand pointer mapping mode (default absolute)")
    p.add_argument("--pointer-margin", type=float, default=0.65,
                   help="Absolute-mode active region as a fraction of the frame "
                        "(default 0.65)")
    p.add_argument("--pointer-gain", type=float, default=2.0,
                   help="Relative-mode cursor gain (default 2.0)")
    p.add_argument("--pointer-k", type=float, default=1.0,
                   help="Fingertip projection distance as a multiple of hand "
                        "size (default 1.0)")
    p.add_argument("--no-pointer", action="store_true",
                   help="Disable the hand mouse pointer feature")
```

- [ ] **Step 2: Add imports**

Near the top of `handvol.pyw`, after the existing `from handvol.voice_search import VoiceSearch` line, add:

```python
from handvol.handmouse import mouse as hm_mouse
from handvol.handmouse.pointer import HandPointer, AbsoluteMapper, RelativeMapper
from handvol.handmouse import detect as hm_detect
```

The existing `from handvol.state import GestureStateMachine, State, Event, ...` line already imports `State` and `Event`, which is all the dispatch code below needs.

- [ ] **Step 3: Build the pointer and mouse inside `capture_loop`**

In `handvol.pyw`, inside `capture_loop`, after the line `machine = GestureStateMachine()`, add:

```python
    # Hand pointer setup. Target the primary monitor for now; the Monitor is a
    # config value so a runtime monitor-switch gesture can change it later.
    hand_pointer = None
    pointer_mouse = None
    pointer_point = None  # last projected point in normalized coords, for overlay
    if not args.no_pointer:
        try:
            monitor = hm_mouse.get_primary_monitor()
            virt = hm_mouse.get_virtual_screen()
            pointer_mouse = hm_mouse.Mouse(monitor, virt)
            if args.pointer_mode == "relative":
                mapper = RelativeMapper(monitor.width, monitor.height,
                                        gain=args.pointer_gain)
            else:
                mapper = AbsoluteMapper(monitor.width, monitor.height,
                                        active=args.pointer_margin)
            hand_pointer = HandPointer(mapper, k=args.pointer_k)
        except Exception as exc:  # pragma: no cover - depends on OS state
            print(f"[handvol] hand pointer disabled: {exc!r}")
            hand_pointer = None
```

- [ ] **Step 4: Dispatch pointer events in the event chain**

In `handvol.pyw`, add these branches to the `if/elif event is ...` chain (place them next to the scrub branches, after `EXIT_SCRUB`):

```python
            elif event is Event.ENTER_POINTER:
                pointer_point = None
                if hand_pointer is not None:
                    hand_pointer.acquire()

            elif event is Event.POINTER_UPDATE:
                if hand_pointer is not None and pointer_mouse is not None and landmarks is not None:
                    action = hand_pointer.process(landmarks, time.monotonic())
                    if action.move is not None:
                        pointer_mouse.move_to(*action.move)
                        pointer_point = hm_detect.projected_point(landmarks, k=args.pointer_k)
                    if action.left_edge == "down":
                        pointer_mouse.left_down()
                    elif action.left_edge == "up":
                        pointer_mouse.left_up()
                    if action.right_edge == "down":
                        pointer_mouse.right_down()
                    elif action.right_edge == "up":
                        pointer_mouse.right_up()
                    if action.scroll:
                        pointer_mouse.scroll(action.scroll)

            elif event is Event.EXIT_POINTER:
                if hand_pointer is not None and pointer_mouse is not None:
                    for button, _ in hand_pointer.release():
                        if button == "left":
                            pointer_mouse.left_up()
                        else:
                            pointer_mouse.right_up()
                pointer_point = None
```

Relative mode resumes from the mapper's internal cursor (centered on acquire), which is good enough; no Win32 cursor read is needed.

- [ ] **Step 5: Draw the pointer overlay**

In `handvol.pyw`, in the `if want_window:` drawing block, add after `draw_lock_state(frame, locked)`:

```python
                if hand_pointer is not None and machine.state is State.POINTER:
                    if isinstance(hand_pointer.mapper, AbsoluteMapper):
                        draw_active_region(frame, args.pointer_margin)
                    draw_pointer(
                        frame, pointer_point,
                        left_bent=hand_pointer._index.bent,
                        right_bent=hand_pointer._middle.bent,
                        scrolling=hand_pointer._scroll_anchor_y is not None,
                    )
```

Add `draw_active_region, draw_pointer` to the overlay import list at the top of `capture_loop`:

```python
    from handvol.overlay import (
        draw_state, draw_gesture, draw_volume, draw_fps,
        draw_landmarks, draw_scrub_indicator, draw_hold_timer, draw_lock_state,
        draw_active_region, draw_pointer,
    )
```

Also ensure `State` is imported in `handvol.pyw` (it already is, via `from handvol.state import GestureStateMachine, State, Event, ...`).

- [ ] **Step 6: Run the full suite (no behavior tests here, but confirm imports compile)**

Run: `python -m pytest -q`
Expected: PASS.

Run: `python -c "import ast; ast.parse(open('handvol.pyw').read()); print('handvol.pyw parses')"`
Expected: prints `handvol.pyw parses`.

- [ ] **Step 7: Commit**

```bash
git add handvol.pyw
git commit -m "feat(handvol): wire hand pointer dispatch, CLI flags, overlay"
```

---

## Task 16: Manual smoke test and tuning

**Files:** none (manual verification)

- [ ] **Step 1: Run the app with the preview window**

Run: `python handvol.pyw --show --debug`
Expected: tray icon appears, preview window opens, existing gestures still work.

- [ ] **Step 2: Verify pointer acquisition**

Make the ASL "U" (index + middle up and together, palm to camera). Expected: after about 5 frames the state shows `POINTER`, a cyan active-region box and a green crosshair appear, and the cursor snaps to your hand.

- [ ] **Step 3: Verify movement, clicks, drag, scroll**

- Move the hand: cursor follows, steady (no jitter).
- Bend index: left click fires; the crosshair turns red; cursor does not jump.
- Bend middle: right click fires.
- Hold index bent while moving: drag works.
- Touch thumb to index base and move up/down: page scrolls; crosshair turns yellow.

- [ ] **Step 4: Verify exit and no stuck buttons**

Drop the pose or show an open palm. Expected: after about 3 frames state returns to `IDLE`, crosshair disappears, and no mouse button is stuck down (test by clicking normally).

- [ ] **Step 5: Tune if needed**

- If the palm-facing gate rejects a real palm-facing U, flip `PALM_SIGN` values in `handvol/handmouse/detect.py`.
- If the cursor sits too far above the fingertips, lower `--pointer-k` (e.g. `0.7`).
- If clicks chatter or miss, adjust `BendTrigger` `engage_deg`/`release_deg` defaults in `handvol/handmouse/pointer.py`.
- If scroll is too fast/slow or inverted, adjust `SCROLL_GAIN` or construct `HandPointer(..., scroll_invert=True)`.

Record any constant changes in a follow-up commit:

```bash
git add -A
git commit -m "tune(handmouse): adjust pointer constants from smoke test"
```

---

## Self-review notes

- **Spec coverage:** anchor at knuckles (Task 1-2), axis projection method A (Task 2), both mappers default absolute (Tasks 7-8, 15), primary monitor as config (Task 15), active region (Task 7), PIP-angle clicks with Schmitt trigger (Tasks 3, 9), faithful button up/down for click/double/drag (Task 10, 15), thumb-touch scroll (Tasks 5, 10), U-sign detection with tilt tolerance and backward rejection (Task 4), POINTER state sticky across click poses (Task 12), OS injection with multi-monitor math (Task 11), CLI flags (Task 15), overlay (Task 14), tests per module. Method B (latched offset) is intentionally deferred as a documented fallback and is not a task.
- **Placeholder note:** No "TBD"/"TODO"/"similar to" placeholders. Tasks 14 and 15 (overlay and threaded entry point) have no unit tests by design, matching the codebase convention that `overlay.py` and `handvol.pyw` are untested; both are verified in the Task 16 manual smoke test.
- **Type consistency:** `PointerAction(move, left_edge, right_edge, scroll)` is produced in Task 10 and consumed in Task 15. `Mouse` methods (`move_to`, `left_down/up`, `right_down/up`, `scroll`) match between Tasks 11 and 15. `AbsoluteMapper`/`RelativeMapper.map(point, just_acquired)` match between Tasks 7-8 and 10.
