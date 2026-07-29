"""Grab a screenshot of the running Timelapser window (dev aid)."""

from __future__ import annotations

import ctypes
import sys
import time

from PIL import ImageGrab

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def find_window(title: str = "Timelapser") -> int:
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value.strip() == title and user32.IsWindowVisible(hwnd):
                rect = ctypes.create_string_buffer(16)
                user32.GetWindowRect(hwnd, rect)
                left, top, right, bottom = ctypes.cast(
                    rect, ctypes.POINTER(ctypes.c_int32 * 4)
                ).contents
                found.append(((right - left) * (bottom - top), hwnd))
        return True

    user32.EnumWindows(callback, 0)
    # The dropdown popup inherits the app title; the main window is the largest.
    return max(found)[1] if found else 0


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "E:/videos/_shot.png"
    hwnd = find_window()
    if not hwnd:
        print("window not found")
        return 1
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.9)

    rect = ctypes.create_string_buffer(16)
    user32.GetWindowRect(hwnd, rect)
    left, top, right, bottom = ctypes.cast(
        rect, ctypes.POINTER(ctypes.c_int32 * 4)
    ).contents
    ImageGrab.grab(bbox=(left, top, right, bottom)).save(out)
    print(f"saved {out} ({right - left}x{bottom - top})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
