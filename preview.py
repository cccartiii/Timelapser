"""Smooth live preview of the selected capture target."""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np
from PIL import Image, ImageTk

from .capture import CaptureSession
from .winenum import CaptureTarget

# ~30fps into the preview slot. UI paints the newest frame each tick.
_PREVIEW_INTERVAL_MS = 33


class PreviewSession:
    """Owns a throttled capture session used only for the on-screen preview."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session: CaptureSession | None = None
        self._target_key: tuple | None = None
        self._error: str | None = None
        self._generation = 0
        self._busy = False

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._busy

    def _key(self, target: CaptureTarget) -> tuple:
        return (target.hwnd, target.monitor_index, target.label)

    def set_target(self, target: CaptureTarget | None, *, cursor: bool = True) -> None:
        if target is None:
            self.stop()
            return

        key = self._key(target)
        with self._lock:
            if self._session is not None and self._target_key == key:
                return
            self._generation += 1
            generation = self._generation
            old = self._session
            self._session = None
            self._target_key = None
            self._error = None
            self._busy = True

        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
            time.sleep(0.12)

        threading.Thread(
            target=self._start,
            args=(target, key, cursor, generation),
            daemon=True,
            name="tl-preview-start",
        ).start()

    def _start(
        self,
        target: CaptureTarget,
        key: tuple,
        cursor: bool,
        generation: int,
    ) -> None:
        try:
            session = CaptureSession(
                target,
                cursor_capture=cursor,
                draw_border=None,
                minimum_update_interval_ms=_PREVIEW_INTERVAL_MS,
            )
            session.start()
            if not session.wait_for_first_frame(5.0):
                session.stop()
                with self._lock:
                    if generation == self._generation:
                        self._error = "No preview yet — is the window visible?"
                        self._busy = False
                return
            with self._lock:
                if generation != self._generation:
                    session.stop()
                    return
                self._session = session
                self._target_key = key
                self._error = None
                self._busy = False
        except Exception as exc:
            with self._lock:
                if generation == self._generation:
                    self._error = str(exc)
                    self._busy = False

    def latest(self) -> np.ndarray | None:
        with self._lock:
            session = self._session
        if session is None:
            return None
        frame, _ = session.latest()
        if frame is None:
            return None
        return frame.copy()

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            session = self._session
            self._session = None
            self._target_key = None
            self._error = None
            self._busy = False
        if session is not None:
            try:
                session.stop()
            except Exception:
                pass
            time.sleep(0.12)


def fit_preview(frame: np.ndarray, max_w: int, max_h: int) -> np.ndarray:
    src_h, src_w = frame.shape[:2]
    if src_w <= 0 or src_h <= 0 or max_w < 2 or max_h < 2:
        return frame
    scale = min(max_w / src_w, max_h / src_h, 1.0)
    new_w = max(2, int(src_w * scale)) & ~1
    new_h = max(2, int(src_h * scale)) & ~1
    if new_w == src_w and new_h == src_h:
        return frame
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)


def bgr_to_photoimage(frame: np.ndarray):
    """BGR numpy -> Tk image via Pillow (Tk PhotoImage cannot decode JPEG)."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return ImageTk.PhotoImage(Image.fromarray(rgb))


class FramePainter:
    """Reuses one Tk image so painting 30 times a second stops reallocating."""

    def __init__(self) -> None:
        self._photo = None
        self._size: tuple[int, int] | None = None

    def to_photo(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        if self._photo is None or self._size != image.size:
            self._photo = ImageTk.PhotoImage(image)
            self._size = image.size
        else:
            self._photo.paste(image)
        return self._photo
