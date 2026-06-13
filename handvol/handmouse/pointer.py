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
