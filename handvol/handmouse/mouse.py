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
