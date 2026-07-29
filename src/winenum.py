"""Enumeration of capturable targets: top-level windows and monitors."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOREDIRECTIONBITMAP = 0x00200000
WS_CHILD = 0x40000000
DWMWA_CLOAKED = 14

_MIN_WINDOW_EDGE = 32

# Shell surfaces that are technically visible top-level windows but are never
# something a user means to record.
_CLASS_BLOCKLIST = frozenset(
    {
        "Progman",
        "WorkerW",
        "Shell_TrayWnd",
        "Shell_SecondaryTrayWnd",
        "Windows.UI.Core.CoreWindow",
        "ApplicationFrameWindow",  # only the empty UWP host; real UWP windows are cloaked-checked below
        "Windows.Internal.Shell.TabProxyWindow",
        "EdgeUiInputTopWndClass",
        "MultitaskingViewFrame",
        "ForegroundStaging",
        "XamlExplorerHostIslandWindow",
        "TaskListThumbnailWnd",
    }
)


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


_get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_get_window_long.restype = ctypes.c_ssize_t
_get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetForegroundWindow.restype = wintypes.HWND

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_MONITOR_PROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
)


@dataclass(frozen=True)
class CaptureTarget:
    """A window or monitor that can be handed to the capture backend."""

    label: str
    hwnd: int | None = None
    monitor_index: int | None = None
    width: int = 0
    height: int = 0

    @property
    def is_monitor(self) -> bool:
        return self.monitor_index is not None

    def __str__(self) -> str:
        if self.width and self.height:
            return f"{self.label}  [{self.width}x{self.height}]"
        return self.label


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _is_cloaked(hwnd: int) -> bool:
    """True for DWM-cloaked windows: suspended UWP apps and other invisible ghosts."""
    cloaked = wintypes.DWORD(0)
    result = dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_CLOAKED),
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return result == 0 and cloaked.value != 0


def _process_name(hwnd: int) -> str:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    try:
        import psutil

        return psutil.Process(pid.value).name()
    except Exception:
        return ""


def window_size(hwnd: int) -> tuple[int, int]:
    """Client-area size of a window, which is what the capture API delivers."""
    rect = RECT()
    if not user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return (0, 0)
    return (rect.right - rect.left, rect.bottom - rect.top)


def window_exists(hwnd: int) -> bool:
    return bool(user32.IsWindow(wintypes.HWND(hwnd)))


def list_windows() -> list[CaptureTarget]:
    """Visible, non-cloaked, titled top-level windows, sorted by process then title."""
    targets: list[CaptureTarget] = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if _get_window_long(hwnd, GWL_STYLE) & WS_CHILD:
            return True
        if _get_window_long(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True

        title = _window_title(hwnd)
        if not title:
            return True
        if _class_name(hwnd) in _CLASS_BLOCKLIST:
            return True
        if _is_cloaked(hwnd):
            return True

        width, height = window_size(hwnd)
        # Minimized windows report a zero/tiny client rect but are still valid
        # capture targets once restored, so keep them and flag them instead.
        minimized = bool(user32.IsIconic(hwnd))
        if not minimized and (width < _MIN_WINDOW_EDGE or height < _MIN_WINDOW_EDGE):
            return True

        proc = _process_name(hwnd)
        label = f"{proc} - {title}" if proc else title
        if minimized:
            label = f"(minimized) {label}"
        targets.append(
            CaptureTarget(label=label, hwnd=int(hwnd), width=width, height=height)
        )
        return True

    user32.EnumWindows(_ENUM_PROC(callback), 0)
    targets.sort(key=lambda t: t.label.lower())
    return targets


def list_monitors() -> list[CaptureTarget]:
    """All active monitors, primary first."""
    found: list[tuple[int, int, int, bool]] = []

    def callback(hmonitor, _hdc, _rect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            width = info.rcMonitor.right - info.rcMonitor.left
            height = info.rcMonitor.bottom - info.rcMonitor.top
            is_primary = bool(info.dwFlags & 1)  # MONITORINFOF_PRIMARY
            found.append((len(found), width, height, is_primary))
        return True

    user32.EnumDisplayMonitors(None, None, _MONITOR_PROC(callback), 0)

    targets = []
    for index, width, height, is_primary in found:
        suffix = " (primary)" if is_primary else ""
        # The capture backend numbers monitors from 1.
        targets.append(
            CaptureTarget(
                label=f"Monitor {index + 1}{suffix}",
                monitor_index=index + 1,
                width=width,
                height=height,
            )
        )
    return targets


def list_targets() -> list[CaptureTarget]:
    """Monitors first, then windows - the full dropdown contents."""
    return list_monitors() + list_windows()


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


if __name__ == "__main__":
    for target in list_targets():
        print(target)
