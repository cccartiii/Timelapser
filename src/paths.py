"""Filesystem locations, intentionally kept off the system drive.

This machine's C: drive runs at near-zero free space, so all temp, cache and
staging paths are anchored to E: whenever possible.
"""

from __future__ import annotations

import os
import sys

PREFERRED_OUTPUT_DIR = r"E:\videos"
APP_DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".build")
CACHE_ROOT = os.path.join(APP_DATA_ROOT, "cache")
SCRATCH_ROOT = os.path.join(APP_DATA_ROOT, "scratch")
LOG_ROOT = os.path.join(APP_DATA_ROOT, "logs")
LEGACY_SCRATCH_ROOT = os.path.join(APP_DATA_ROOT, "scratch")


def app_dir() -> str:
    """Directory holding the exe when frozen, or the project root in dev."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _drive_of(path: str) -> str:
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return drive or "E:"


def cache_dir() -> str:
    """Persistent cache location for app/runtime data."""
    try:
        return _ensure(CACHE_ROOT)
    except OSError:
        return _ensure(os.path.join(_drive_of(app_dir()) + os.sep, "timelapser-cache"))


def scratch_dir() -> str:
    """Working directory for temp files."""
    try:
        return _ensure(SCRATCH_ROOT)
    except OSError:
        try:
            return _ensure(LEGACY_SCRATCH_ROOT)
        except OSError:
            return _ensure(os.path.join(_drive_of(app_dir()) + os.sep, "timelapser-scratch"))


def log_dir() -> str:
    """Persistent log location for app/runtime diagnostics."""
    try:
        return _ensure(LOG_ROOT)
    except OSError:
        return _ensure(os.path.join(_drive_of(app_dir()) + os.sep, "timelapser-logs"))


def child_env() -> dict:
    """Environment for ffmpeg with temp/cache redirected away from C:."""
    env = dict(os.environ)
    scratch = scratch_dir()
    cache = cache_dir()
    env["TEMP"] = scratch
    env["TMP"] = scratch
    env["TMPDIR"] = scratch
    env["PYTHONPYCACHEPREFIX"] = os.path.join(cache, "pycache")
    env["XDG_CACHE_HOME"] = cache
    return env


def default_output_dir() -> str:
    """Where recordings land by default."""
    if os.path.isdir(PREFERRED_OUTPUT_DIR):
        return PREFERRED_OUTPUT_DIR
    drive = _drive_of(app_dir())
    candidate = os.path.join(drive + os.sep, "videos")
    if os.path.isdir(candidate):
        return candidate
    return app_dir()


def free_space_bytes(path: str) -> int:
    try:
        import shutil

        return shutil.disk_usage(path).free
    except OSError:
        return -1
