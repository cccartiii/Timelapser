"""Windows Graphics Capture session wrapped behind a thread-safe latest-frame slot."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np
from windows_capture import WindowsCapture

from .winenum import CaptureTarget


@dataclass
class CaptureStats:
    frames_received: int = 0
    last_error: str | None = None
    closed: bool = False


class CaptureSession:
    """Runs a WGC capture on its own thread and keeps only the most recent frame.

    The buffer handed to `on_frame_arrived` is a numpy view over memory owned by
    the native layer and is invalidated as soon as the callback returns, so the
    frame is copied out immediately. Only the newest frame is retained: the
    sampler decides how often to actually consume one.
    """

    def __init__(
        self,
        target: CaptureTarget,
        *,
        cursor_capture: bool | None = True,
        draw_border: bool | None = None,
        minimum_update_interval_ms: int | None = None,
    ) -> None:
        self.target = target
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._sequence = 0
        self._control = None
        self._started = False
        self.stats = CaptureStats()
        self.first_frame_event = threading.Event()
        self.warnings: list[str] = []

        self._kwargs = {
            "cursor_capture": cursor_capture,
            "draw_border": draw_border,
            "minimum_update_interval": minimum_update_interval_ms,
        }
        if target.is_monitor:
            self._kwargs["monitor_index"] = target.monitor_index
        else:
            self._kwargs["window_hwnd"] = target.hwnd

    def _build(self, kwargs: dict) -> WindowsCapture:
        capture = WindowsCapture(**kwargs)
        # The @event decorator dispatches on function name; assigning the
        # handler attributes directly is the supported alternative.
        capture.frame_handler = self._on_frame_arrived
        capture.closed_handler = self._on_closed
        return capture

    def _on_frame_arrived(self, frame, _capture_control) -> None:
        # BGRA view -> contiguous BGR copy that outlives this callback.
        bgr = np.ascontiguousarray(frame.frame_buffer[:, :, :3])
        with self._lock:
            self._frame = bgr
            self._sequence += 1
            self.stats.frames_received += 1
        self.first_frame_event.set()

    def _on_closed(self) -> None:
        self.stats.closed = True
        # Unblock anyone waiting on a first frame that will now never arrive.
        self.first_frame_event.set()

    def start(self) -> None:
        """Start capturing, dropping optional toggles the OS build rejects.

        `draw_border` and `cursor_capture` map to Graphics Capture properties
        that older Windows 10 builds do not expose; asking for them throws
        rather than being ignored, so retry without them.
        """
        attempts: list[tuple[dict, tuple[str, ...]]] = [(dict(self._kwargs), ())]
        kwargs = dict(self._kwargs)
        dropped: list[str] = []
        for optional in ("draw_border", "cursor_capture"):
            if kwargs.get(optional) is None:
                continue
            kwargs = dict(kwargs)
            kwargs[optional] = None
            dropped.append(optional)
            attempts.append((kwargs, tuple(dropped)))

        last_error: Exception | None = None
        for attempt_kwargs, dropped_names in attempts:
            self.stats.closed = False
            self.first_frame_event.clear()
            try:
                self._capture = self._build(attempt_kwargs)
                self._control = self._capture.start_free_threaded()
            except Exception as exc:
                last_error = exc
                if "not supported" not in str(exc).lower():
                    raise
                continue
            self._started = True
            for name in dropped_names:
                self.warnings.append(
                    f"'{name.replace('_', ' ')}' is not supported on this Windows "
                    "version - continuing without it"
                )
            return

        raise last_error if last_error else RuntimeError("Unable to start capture")

    def latest(self) -> tuple[np.ndarray | None, int]:
        """The most recent frame and its sequence number (0 if none yet)."""
        with self._lock:
            return self._frame, self._sequence

    def wait_for_first_frame(self, timeout: float) -> bool:
        return self.first_frame_event.wait(timeout) and self._frame is not None

    @property
    def is_closed(self) -> bool:
        return self.stats.closed

    def stop(self, timeout: float = 5.0) -> None:
        """Stop capturing and wait for the native thread to actually finish.

        `stop()` only signals; returning before the session has released its
        Direct3D resources lets a subsequent session overlap with this one,
        which crashes the capture backend.
        """
        if not self._started or self._control is None:
            return
        control = self._control
        try:
            control.stop()
        except Exception as exc:  # the session may already have torn itself down
            self.stats.last_error = str(exc)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if control.is_finished():
                    break
            except Exception:
                break
            time.sleep(0.02)
        else:
            self.stats.last_error = "capture thread did not stop within timeout"

        self._started = False
        self._control = None


def suggest_update_interval_ms(sample_period_s: float) -> int:
    """Throttle the capture API so it does not deliver frames we would discard.

    Half the sample period keeps a fresh frame available at every sample tick
    while sparing the GPU a full-rate stream during a slow timelapse. An
    explicit value is always returned: leaving the interval unset takes a
    different path through the capture backend that proved unstable when a
    session is created after earlier ones have been torn down.
    """
    interval = int(sample_period_s * 1000 / 2)
    return max(4, min(interval, 1000))
