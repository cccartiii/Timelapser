"""High-resolution, cancellable waiting.

Windows' default timer granularity is ~15.6ms, so a plain `Event.wait(1/60)`
sleeps for roughly 34ms and a "60fps" loop actually runs at about 30fps. This
module wraps a high-resolution waitable timer and waits on it together with a
cancellation event, giving sub-millisecond pacing that still aborts instantly
when recording stops.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm")

CREATE_WAITABLE_TIMER_HIGH_RESOLUTION = 0x00000002
TIMER_ALL_ACCESS = 0x1F0003
INFINITE = 0xFFFFFFFF
WAIT_OBJECT_0 = 0

kernel32.CreateWaitableTimerExW.restype = wintypes.HANDLE
kernel32.CreateWaitableTimerExW.argtypes = [
    wintypes.LPVOID,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
]
kernel32.SetWaitableTimer.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(ctypes.c_longlong),
    ctypes.c_long,
    wintypes.LPVOID,
    wintypes.LPVOID,
    wintypes.BOOL,
]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [
    wintypes.LPVOID,
    wintypes.BOOL,
    wintypes.BOOL,
    wintypes.LPCWSTR,
]
kernel32.WaitForMultipleObjects.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.BOOL,
    wintypes.DWORD,
]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class TimerResolution:
    """Raises the system timer resolution for the lifetime of the block.

    This affects thread scheduling generally, so it is held only while
    recording and always released afterwards.
    """

    def __init__(self, milliseconds: int = 1) -> None:
        self.milliseconds = milliseconds
        self._active = False

    def __enter__(self) -> "TimerResolution":
        if winmm.timeBeginPeriod(self.milliseconds) == 0:
            self._active = True
        return self

    def __exit__(self, *exc_info) -> None:
        if self._active:
            winmm.timeEndPeriod(self.milliseconds)
            self._active = False


class PreciseWaiter:
    """A cancellable sleep with sub-millisecond accuracy."""

    def __init__(self) -> None:
        self._timer = kernel32.CreateWaitableTimerExW(
            None, None, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS
        )
        if not self._timer:
            # Pre-1803 Windows has no high-resolution flag; a normal timer is
            # still better than nothing.
            self._timer = kernel32.CreateWaitableTimerExW(None, None, 0, TIMER_ALL_ACCESS)
        self._cancel = kernel32.CreateEventW(None, True, False, None)
        self._closed = False

    def cancel(self) -> None:
        if not self._closed:
            kernel32.SetEvent(self._cancel)

    @property
    def cancelled(self) -> bool:
        return kernel32.WaitForSingleObject(self._cancel, 0) == WAIT_OBJECT_0

    def wait(self, seconds: float) -> bool:
        """Sleep for `seconds`. Returns True if cancelled instead of elapsing."""
        if self._closed:
            return True
        if seconds <= 0:
            return self.cancelled

        # Negative relative due time, in 100-nanosecond units.
        due = ctypes.c_longlong(int(-seconds * 10_000_000))
        if not kernel32.SetWaitableTimer(self._timer, ctypes.byref(due), 0, None, None, False):
            return self.cancelled

        handles = (wintypes.HANDLE * 2)(self._timer, self._cancel)
        result = kernel32.WaitForMultipleObjects(2, handles, False, INFINITE)
        return result == WAIT_OBJECT_0 + 1

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for handle in (self._timer, self._cancel):
            if handle:
                kernel32.CloseHandle(handle)
