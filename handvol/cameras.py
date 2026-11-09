"""Enumerate DirectShow video capture devices.

The order matches OpenCV's CAP_DSHOW device indices, so list position i is
the index to pass to cv2.VideoCapture(i, cv2.CAP_DSHOW).
"""

import ctypes
from ctypes import POINTER, HRESULT, byref, c_ulong, c_void_p
from ctypes.wintypes import DWORD

# Substring (lowercase) marking software cameras that usually feed nothing
# useful by default: Windows Phone Link ("Windows Virtual Camera") and OBS.
VIRTUAL_MARKERS = ("virtual camera",)


_COM_CACHE = {}


def _com():
    """Build the DirectShow COM interface declarations once and cache them."""
    if _COM_CACHE:
        return _COM_CACHE
    from comtypes import COMMETHOD, GUID, IUnknown
    from comtypes.automation import VARIANT

    class IPropertyBag(IUnknown):
        _iid_ = GUID("{55272A00-42CB-11CE-8135-00AA004BB851}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Read",
                      (["in"], ctypes.c_wchar_p, "name"),
                      (["in"], POINTER(VARIANT), "var"),
                      (["in"], c_void_p, "log")),
            COMMETHOD([], HRESULT, "Write",
                      (["in"], ctypes.c_wchar_p),
                      (["in"], POINTER(VARIANT))),
        ]

    class IMoniker(IUnknown):
        _iid_ = GUID("{0000000f-0000-0000-C000-000000000046}")
        # IPersist + IPersistStream slots precede BindToStorage; they are
        # declared only to keep the vtable offsets right.
        _methods_ = [
            COMMETHOD([], HRESULT, "GetClassID", (["out"], POINTER(GUID))),
            COMMETHOD([], HRESULT, "IsDirty"),
            COMMETHOD([], HRESULT, "Load", (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "Save", (["in"], c_void_p), (["in"], ctypes.c_int)),
            COMMETHOD([], HRESULT, "GetSizeMax", (["out"], POINTER(ctypes.c_ulonglong))),
            COMMETHOD([], HRESULT, "BindToObject",
                      (["in"], c_void_p), (["in"], c_void_p),
                      (["in"], POINTER(GUID)), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "BindToStorage",
                      (["in"], c_void_p), (["in"], c_void_p),
                      (["in"], POINTER(GUID)), (["out"], POINTER(POINTER(IUnknown)))),
        ]

    class IEnumMoniker(IUnknown):
        _iid_ = GUID("{00000102-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Next",
                      (["in"], c_ulong, "celt"),
                      (["out"], POINTER(POINTER(IMoniker)), "rgelt"),
                      (["out"], POINTER(c_ulong), "fetched")),
        ]

    class ICreateDevEnum(IUnknown):
        _iid_ = GUID("{29840822-5B84-11D0-BD3B-00A0C911CE86}")
        _methods_ = [
            COMMETHOD([], HRESULT, "CreateClassEnumerator",
                      (["in"], POINTER(GUID)),
                      (["out"], POINTER(POINTER(IEnumMoniker))),
                      (["in"], DWORD)),
        ]

    _COM_CACHE.update(
        IPropertyBag=IPropertyBag,
        ICreateDevEnum=ICreateDevEnum,
        VARIANT=VARIANT,
        clsid_system_device_enum=GUID("{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}"),
        clsid_video_input_category=GUID("{860BB310-5D01-11d0-BD3B-00A0C911CE86}"),
    )
    return _COM_CACHE


def _monikers():
    """Return the video-input device monikers in CAP_DSHOW index order."""
    import comtypes
    from comtypes import CoCreateInstance

    com = _com()
    try:
        comtypes.CoInitialize()
    except OSError:
        pass  # already initialized on this thread in another mode
    dev_enum = CoCreateInstance(com["clsid_system_device_enum"],
                                interface=com["ICreateDevEnum"])
    enum = dev_enum.CreateClassEnumerator(byref(com["clsid_video_input_category"]), 0)
    monikers = []
    if not enum:  # S_FALSE: no devices in the category
        return monikers
    while True:
        try:
            moniker, fetched = enum.Next(1)
        except comtypes.COMError:
            break
        if not fetched:
            break
        monikers.append(moniker)
    return monikers


def _friendly_name(moniker):
    """Read one device's FriendlyName from its property bag."""
    com = _com()
    bag = moniker.BindToStorage(
        None, None, byref(com["IPropertyBag"]._iid_)).QueryInterface(com["IPropertyBag"])
    var = com["VARIANT"]()
    bag.Read("FriendlyName", byref(var), None)
    return str(var.value)


def _enumerate_dshow():
    import comtypes

    names = []
    for moniker in _monikers():
        # Always append one entry per moniker so list position i stays equal
        # to CAP_DSHOW index i, even when a device's name is unreadable.
        try:
            names.append(_friendly_name(moniker))
        except comtypes.COMError:
            names.append(f"Camera {len(names)}")
    return names


def list_cameras():
    """Return camera friendly names in CAP_DSHOW index order ([] on failure)."""
    try:
        return _enumerate_dshow()
    except Exception as exc:  # COM / ctypes failures must never crash the app
        print(f"[handvol] camera enumeration failed: {exc!r}")
        return []


def is_virtual(name):
    lowered = name.lower()
    return any(marker in lowered for marker in VIRTUAL_MARKERS)


def resolve_index(names, name):
    """Return the index of the first entry equal to name, or None if absent."""
    for i, candidate in enumerate(names):
        if candidate == name:
            return i
    return None


def choose_camera(names, saved_name=None, cli_index=None):
    """Pick the startup camera index.

    Priority: explicit CLI index > saved name (if present now and not a
    virtual camera) > first non-virtual camera > 0. Duplicate names resolve
    to the first match. A saved virtual camera is ignored so a disconnected
    phone's leftover "Windows Virtual Camera" never wins on the next launch.
    """
    if cli_index is not None:
        return cli_index
    if saved_name and not is_virtual(saved_name):
        i = resolve_index(names, saved_name)
        if i is not None:
            return i
    for i, name in enumerate(names):
        if not is_virtual(name):
            return i
    return 0
