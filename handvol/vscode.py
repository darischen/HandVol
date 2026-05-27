"""Find-or-launch Visual Studio Code on Windows.

Mirrors ``discord.py`` / ``spotify.py``: focus the existing main window if VS
Code is running, otherwise launch it from the standard install location.
Supports the regular and Insiders builds.
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

# Both stable and Insiders builds. The Insiders exe literally has a space and
# hyphen in the filename; comparison is case-insensitive via .lower().
VSCODE_EXE_NAMES = ("code.exe", "code - insiders.exe")


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


def _find_vscode_hwnd():
    """Top-level visible Code.exe window with a non-empty title.

    VS Code (Electron) spawns several helper processes named Code.exe too,
    but only the main one owns a visible window with a real title.
    """
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_exe(pid.value)
        if exe and os.path.basename(exe).lower() in VSCODE_EXE_NAMES:
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


def _vscode_exe_path():
    """First existing Code.exe across user/system/Insiders installs, or None."""
    local = os.environ.get("LOCALAPPDATA")
    pf = os.environ.get("ProgramFiles")
    pf86 = os.environ.get("ProgramFiles(x86)")
    candidates = []
    if local:
        candidates.append(os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe"))
        candidates.append(os.path.join(local, "Programs", "Microsoft VS Code Insiders", "Code - Insiders.exe"))
    if pf:
        candidates.append(os.path.join(pf, "Microsoft VS Code", "Code.exe"))
        candidates.append(os.path.join(pf, "Microsoft VS Code Insiders", "Code - Insiders.exe"))
    if pf86:
        candidates.append(os.path.join(pf86, "Microsoft VS Code", "Code.exe"))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def focus_or_launch():
    """Bring VS Code to focus if running; launch it otherwise. Returns one of
    'focused', 'launched', 'failed' for logging."""
    hwnd = _find_vscode_hwnd()
    if hwnd:
        try:
            _force_foreground(hwnd)
            return "focused"
        except Exception:
            return "failed"
    exe = _vscode_exe_path()
    if exe is None:
        return "failed"
    try:
        subprocess.Popen([exe], close_fds=True)
        return "launched"
    except OSError:
        return "failed"
