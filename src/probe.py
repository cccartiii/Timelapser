"""Report Timelapser window geometry over time (dev aid)."""

from __future__ import annotations

import ctypes
import sys
import time

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def windows(match: str = "imelapse"):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if match in buffer.value:
                rect = ctypes.create_string_buffer(16)
                user32.GetWindowRect(hwnd, rect)
                box = tuple(
                    ctypes.cast(rect, ctypes.POINTER(ctypes.c_int32 * 4)).contents
                )
                found.append(
                    (
                        buffer.value,
                        box,
                        bool(user32.IsWindowVisible(hwnd)),
                        bool(user32.IsIconic(hwnd)),
                    )
                )
        return True

    user32.EnumWindows(callback, 0)
    return found


def main() -> int:
    for step in range(int(sys.argv[1]) if len(sys.argv) > 1 else 6):
        print(f"t={step}s")
        for title, box, visible, iconic in windows():
            size = (box[2] - box[0], box[3] - box[1])
            print(f"   {title!r} size={size} pos={box[:2]} vis={visible} min={iconic}")
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
