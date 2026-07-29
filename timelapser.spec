# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Timelapser.

Everything is pinned to the E: drive on purpose. The system drive on this
machine has almost no free space, and a onefile executable normally unpacks
itself into %TEMP% on every launch, which would fail. `runtime_tmpdir` moves
that unpack directory onto E:.
"""

import os
import shutil

PROJECT_DIR = os.path.abspath(os.getcwd())
APP_DATA_ROOT = os.path.join(PROJECT_DIR, ".build")
STAGING_DIR = os.path.join(APP_DATA_ROOT, "build", "staging")
RUNTIME_TMPDIR = os.path.join(APP_DATA_ROOT, "runtime-tmp")

os.makedirs(STAGING_DIR, exist_ok=True)
os.makedirs(RUNTIME_TMPDIR, exist_ok=True)


def _staged_ffmpeg() -> str:
    """Copy the imageio-ffmpeg binary in under a predictable name.

    The wheel ships it as ffmpeg-win-x86_64-v7.1.exe; the app looks for a plain
    ffmpeg.exe at the root of the bundle.
    """
    from imageio_ffmpeg import get_ffmpeg_exe

    source = get_ffmpeg_exe()
    target = os.path.join(STAGING_DIR, "ffmpeg.exe")
    if not os.path.exists(target) or os.path.getmtime(source) > os.path.getmtime(target):
        shutil.copy2(source, target)
    return target


binaries = [(_staged_ffmpeg(), ".")]

hiddenimports = [
    "windows_capture",
    "keyboard",
    "psutil",
    "cv2",
    "numpy",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "timelapser.theme",
    "timelapser.widgets",
    "timelapser.loader",
    "timelapser.preview",
]

# Large scientific and media packages that happen to share this interpreter but
# are never imported by Timelapser.
excludes = [
    "matplotlib",
    "scipy",
    "numba",
    "llvmlite",
    "librosa",
    "sklearn",
    "pandas",
    "IPython",
    "notebook",
    "soundfile",
    "soxr",
    "audioread",
    "pooch",
    "mido",
    "serial",
    "usb",
    "flask",
    "werkzeug",
    "jinja2",
    "yt_dlp",
    "requests",
    "urllib3",
    "pyautogui",
    "pygetwindow",
    "pyscreeze",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "imageio",
    "pytest",
    "setuptools",
    "pip",
]

ICON_PATH = os.path.join(PROJECT_DIR, "assets", "timelapser.ico")

a = Analysis(
    ["run_timelapser.py"],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=[
        (os.path.join(PROJECT_DIR, "assets", "timelapser.ico"), "assets"),
        (os.path.join(PROJECT_DIR, "assets", "timelapser.png"), "assets"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Timelapser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=RUNTIME_TMPDIR,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if os.path.isfile(ICON_PATH) else None,
)
