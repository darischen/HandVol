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
