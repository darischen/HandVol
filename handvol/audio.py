from ctypes import cast, POINTER

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


_volume_ctrl = None


def _ctrl():
    global _volume_ctrl
    if _volume_ctrl is None:
        devices = AudioUtilities.GetSpeakers()
        # Newer pycaw wraps IMMDevice in AudioDevice; the COM Activate lives on ._dev.
        raw = getattr(devices, "_dev", devices)
        interface = raw.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
    return _volume_ctrl


def _reset_ctrl():
    global _volume_ctrl
    _volume_ctrl = None


def set_volume(percent):
    global _volume_ctrl
    percent = max(0.0, min(100.0, float(percent)))
    try:
        _ctrl().SetMasterVolumeLevelScalar(percent / 100.0, None)
    except Exception:
        _reset_ctrl()
        raise


def get_volume():
    global _volume_ctrl
    try:
        return _ctrl().GetMasterVolumeLevelScalar() * 100.0
    except Exception:
        _reset_ctrl()
        raise


def toggle_mute():
    global _volume_ctrl
    try:
        c = _ctrl()
        c.SetMute(not c.GetMute(), None)
    except Exception:
        _reset_ctrl()
        raise


def is_muted():
    global _volume_ctrl
    try:
        return bool(_ctrl().GetMute())
    except Exception:
        _reset_ctrl()
        raise
