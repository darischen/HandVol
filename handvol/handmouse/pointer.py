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


class RelativeMapper:
    """Trackpad-style mapping: adds gain-scaled hand deltas to the cursor.
    On re-acquisition it resets the reference point so the cursor resumes from
    where it sits instead of jumping -- the clutch."""

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


class BendTrigger:
    """Schmitt trigger over a scalar bend signal (a fingertip-curl ratio).
    Becomes 'bent' only after the value drops below `engage`, and 'straight'
    again only after it rises back above `release`. The gap (engage < release)
    stops a single bend from chattering into multiple click events."""

    def __init__(self, engage=0.7, release=0.95):
        self.engage = engage
        self.release = release
        self.bent = False

    def update(self, value):
        if self.bent:
            if value > self.release:
                self.bent = False
        else:
            if value < self.engage:
                self.bent = True
        return self.bent

    def reset(self):
        self.bent = False


from collections import namedtuple

from handvol.handmouse import detect

PointerAction = namedtuple("PointerAction", "move left_edge right_edge scroll")
PointerStatus = namedtuple(
    "PointerStatus", "point left_bent right_bent scrolling scroll_anchor_y")

# Fingertip-curl ratios for the Schmitt click trigger. The finger reads "bent"
# (button down) once the tip/dip/pip hook below CURL_ENGAGE and "straight"
# (button up) again above CURL_RELEASE.
CURL_ENGAGE = 0.7
CURL_RELEASE = 0.95

# Wheel notches per unit of normalized displacement per second. Scroll is a
# velocity: the farther the hand sits from the anchor set when scrolling began,
# the faster it scrolls. Tunable; far lower than a per-frame increment.
SCROLL_GAIN = 60.0


class HandPointer:
    """Turns per-frame landmarks into a PointerAction: where to move, click
    edges (down/up transitions), and scroll ticks. Holds smoothing filters, the
    active screen mapper, bend triggers, and scroll state. Clicks are derived
    from fingertip-curl geometry, never from gesture labels. Scroll engages
    when the thumb is raised and scrolls at a speed set by how far the hand is
    from the anchor captured at engage time."""

    def __init__(self, mapper, k=1.0, scroll_gain=SCROLL_GAIN, scroll_invert=False):
        self.mapper = mapper
        self.k = k
        self.scroll_gain = scroll_gain
        self.scroll_invert = scroll_invert
        self._fx = OneEuroFilter(min_cutoff=1.0, beta=0.7, d_cutoff=1.0)
        self._fy = OneEuroFilter(min_cutoff=1.0, beta=0.7, d_cutoff=1.0)
        self._index = BendTrigger(engage=CURL_ENGAGE, release=CURL_RELEASE)
        self._middle = BendTrigger(engage=CURL_ENGAGE, release=CURL_RELEASE)
        self._just_acquired = True
        self._scroll_anchor_y = None
        self._scroll_accum = 0.0
        self._t_prev = None
        self._sx = None
        self._sy = None
        self._scrolling = False
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
        self._scroll_accum = 0.0
        self._t_prev = None
        self._sx = None
        self._sy = None
        self._scrolling = False

    def process(self, landmarks, t):
        px, py = detect.projected_point(landmarks, k=self.k)
        sx = self._fx(px, t)
        sy = self._fy(py, t)
        self._sx, self._sy = sx, sy
        dt = 0.0 if self._t_prev is None else max(1e-3, t - self._t_prev)
        self._t_prev = t

        if detect.thumb_extended(landmarks):
            self._scrolling = True
            # Engaging scroll releases any button still held from a click/drag,
            # so a button cannot stay down while scrolling.
            left_edge = right_edge = None
            if self._left_down:
                self._left_down = False
                self._index.reset()
                left_edge = "up"
            if self._right_down:
                self._right_down = False
                self._middle.reset()
                right_edge = "up"
            if self._scroll_anchor_y is None:
                self._scroll_anchor_y = sy
                self._scroll_accum = 0.0
                return PointerAction(None, left_edge, right_edge, 0)
            # Velocity: displacement from the fixed anchor sets scroll speed.
            displacement = self._scroll_anchor_y - sy  # hand above anchor -> +
            self._scroll_accum += displacement * self.scroll_gain * dt
            ticks = int(self._scroll_accum)
            self._scroll_accum -= ticks  # keep the sub-notch remainder
            if self.scroll_invert:
                ticks = -ticks
            return PointerAction(None, left_edge, right_edge, ticks)

        self._scrolling = False
        self._scroll_anchor_y = None
        self._scroll_accum = 0.0

        index_curl = detect.fingertip_curl(
            landmarks, detect.INDEX_MCP, detect.INDEX_PIP, detect.INDEX_TIP)
        middle_curl = detect.fingertip_curl(
            landmarks, detect.MIDDLE_MCP, detect.MIDDLE_PIP, detect.MIDDLE_TIP)
        left_edge = self._edge(self._index, index_curl, "left")
        right_edge = self._edge(self._middle, middle_curl, "right")

        move = self.mapper.map((sx, sy), self._just_acquired)
        self._just_acquired = False
        return PointerAction(move, left_edge, right_edge, 0)

    def _edge(self, trigger, value, button):
        was = trigger.bent
        now = trigger.update(value)
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

    def status(self):
        """Snapshot for the overlay: the smoothed cursor point, button-held
        flags, and scroll state. Lets the UI draw without poking internals."""
        point = (self._sx, self._sy) if self._sx is not None else None
        return PointerStatus(point, self._index.bent, self._middle.bent,
                             self._scrolling, self._scroll_anchor_y)

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
