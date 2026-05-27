"""Find-or-launch Discord on Windows.

If Discord is already running, bring its main window to the foreground without
moving it. Otherwise launch via the Squirrel updater stub at
``%LOCALAPPDATA%\\Discord\\Update.exe``, which is the standard per-user install
path — Discord has no system-wide URI scheme for plain launch.
"""
import ctypes
import os
import subprocess
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD,
    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]

# Discord ships canary/PTB builds with distinct exe names; match any of them so
# the focus path works regardless of which channel the user installed.
DISCORD_EXE_NAMES = ("discord.exe", "discordcanary.exe", "discordptb.exe")


def _process_exe(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        kernel32.CloseHandle(h)


def _find_discord_hwnd():
    """Top-level visible window owned by a Discord process with a non-empty title."""
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_exe(pid.value)
        if exe and os.path.basename(exe).lower() in DISCORD_EXE_NAMES:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else None


def _force_foreground(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    my_tid = kernel32.GetCurrentThreadId()

    attached = False
    if fg_tid and fg_tid != my_tid:
        attached = bool(user32.AttachThreadInput(my_tid, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(my_tid, fg_tid, False)


def _discord_updater_path():
    """Return the first existing Update.exe across stable/PTB/canary, or None."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    for folder, exe in (
        ("Discord", "Discord.exe"),
        ("DiscordPTB", "DiscordPTB.exe"),
        ("DiscordCanary", "DiscordCanary.exe"),
    ):
        updater = os.path.join(local, folder, "Update.exe")
        if os.path.exists(updater):
            return updater, exe
    return None


def focus_or_launch():
    """Bring Discord to focus if running; launch it otherwise. Returns one of
    'focused', 'launched', 'failed' for logging."""
    hwnd = _find_discord_hwnd()
    if hwnd:
        try:
            _force_foreground(hwnd)
            return "focused"
        except Exception:
            return "failed"
    updater = _discord_updater_path()
    if updater is None:
        return "failed"
    path, exe = updater
    try:
        subprocess.Popen([path, "--processStart", exe], close_fds=True)
        return "launched"
    except OSError:
        return "failed"
