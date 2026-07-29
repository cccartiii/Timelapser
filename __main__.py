"""Application entry point."""

from __future__ import annotations

import ctypes
import os
import sys

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2


def enable_dpi_awareness() -> None:
    """Opt into per-monitor DPI so the UI is crisp and window rects are true pixels."""
    user32 = ctypes.windll.user32
    try:
        if user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        ):
            return
    except AttributeError:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        return
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass


def _redirect_temp() -> None:
    """Keep every temp and cache file on E: when possible."""
    import tempfile

    from timelapser.paths import cache_dir, scratch_dir

    try:
        scratch = scratch_dir()
        cache = cache_dir()
    except OSError:
        return
    os.environ["TEMP"] = scratch
    os.environ["TMP"] = scratch
    os.environ["TMPDIR"] = scratch
    os.environ["PYTHONPYCACHEPREFIX"] = os.path.join(cache, "pycache")
    os.environ["XDG_CACHE_HOME"] = cache
    tempfile.tempdir = scratch


def _report_fatal(exc: BaseException) -> None:
    """Windowed builds have no console, so persist the traceback to E:."""
    import traceback

    text = "".join(traceback.format_exception(exc))
    try:
        from timelapser.paths import log_dir

        log_path = os.path.join(log_dir(), "timelapser-crash.log")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    except OSError:
        log_path = "(could not write log)"

    print(text, file=sys.stderr)
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            f"{text}\n\nWritten to:\n{log_path}",
            "Timelapser - fatal error",
            0x10,
        )
    except Exception:
        pass


def main() -> int:
    if sys.platform != "win32":
        print("Timelapser requires Windows.", file=sys.stderr)
        return 1

    enable_dpi_awareness()
    _redirect_temp()

    try:
        from timelapser.ui import run

        run()
    except BaseException as exc:  # noqa: BLE001 - last resort reporting
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        _report_fatal(exc)
        return 1
    return 0


if __name__ == "__main__":
    # Allow `python -m timelapser` as well as the frozen launcher.
    sys.exit(main())
