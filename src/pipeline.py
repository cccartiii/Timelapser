"""Recording pipeline: sample the capture on a fixed clock and feed the encoder."""

from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from .capture import CaptureSession, suggest_update_interval_ms
from .clock import PreciseWaiter, TimerResolution
from .encoder import Encoder, FFmpegWriter, select_encoder
from .paths import free_space_bytes
from .winenum import CaptureTarget

MODE_SPEED = "speed"
MODE_INTERVAL = "interval"
MODE_REALTIME = "realtime"

RESOLUTIONS: dict[str, tuple[int, int] | None] = {
    "1080p (1920x1080)": (1920, 1080),
    "1440p (2560x1440)": (2560, 1440),
    "720p (1280x720)": (1280, 720),
    "Native (source size)": None,
}

_QUEUE_CAPACITY = 90
_MIN_FREE_BYTES = 300 * 1024 * 1024
_STOP = object()


@dataclass
class RecordingConfig:
    target: CaptureTarget
    output_path: str
    mode: str = MODE_SPEED
    speed: float = 20.0
    interval_s: float = 2.0
    output_fps: int = 60
    resolution: tuple[int, int] | None = (1920, 1080)
    cursor_capture: bool = True
    draw_border: bool = False
    force_cpu: bool = False

    @property
    def sample_period(self) -> float:
        """Seconds of real time between the frames that reach the video."""
        if self.mode == MODE_INTERVAL:
            return max(0.02, self.interval_s)
        if self.mode == MODE_REALTIME:
            return 1.0 / self.output_fps
        return max(0.02, self.speed / self.output_fps)

    @property
    def demand_fps(self) -> float:
        return 1.0 / self.sample_period

    @property
    def effective_speed(self) -> float:
        """How many seconds of real time each second of video represents."""
        return self.sample_period * self.output_fps

    def describe(self) -> str:
        speed = self.effective_speed
        period = self.sample_period
        if self.mode == MODE_REALTIME:
            return f"Realtime 1x at {self.output_fps}fps"
        if period >= 1:
            rate = f"1 frame every {period:.2f}s"
        else:
            rate = f"{1 / period:.1f} frames/s"
        return f"{speed:.0f}x speed - {rate} into a {self.output_fps}fps video"


@dataclass
class RecordingStats:
    state: str = "idle"
    elapsed_s: float = 0.0
    frames_written: int = 0
    frames_dropped: int = 0
    source_frames: int = 0
    output_bytes: int = 0
    encoder_label: str = ""
    resolution: tuple[int, int] = (0, 0)
    error: str | None = None
    output_path: str = ""

    @property
    def video_seconds(self) -> float:
        return self._video_seconds

    _video_seconds: float = field(default=0.0, repr=False)


class Recorder:
    """Owns the capture session, the sampler thread and the encoder writer thread."""

    def __init__(self, config: RecordingConfig) -> None:
        self.config = config
        self.logs: queue.Queue[str] = queue.Queue()
        self._frames: queue.Queue = queue.Queue(maxsize=_QUEUE_CAPACITY)
        self._stop_event = threading.Event()
        self._waiter = PreciseWaiter()
        self._session: CaptureSession | None = None
        self._writer: FFmpegWriter | None = None
        self._sampler: threading.Thread | None = None
        self._writer_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._state = "idle"
        self._error: str | None = None
        self._started_at = 0.0
        self._finished_at = 0.0
        self._frames_dropped = 0
        self._out_size = (0, 0)
        self._encoder: Encoder | None = None

    def log(self, message: str) -> None:
        self.logs.put(message)

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def _set_state(self, state: str) -> None:
        with self._lock:
            self._state = state

    @property
    def is_active(self) -> bool:
        return self.state in ("starting", "recording", "stopping")

    def start(self) -> None:
        if self.is_active:
            raise RuntimeError("already recording")
        self._set_state("starting")
        threading.Thread(target=self._startup, daemon=True, name="tl-startup").start()

    def _startup(self) -> None:
        cfg = self.config
        try:
            out_dir = os.path.dirname(os.path.abspath(cfg.output_path)) or "."
            os.makedirs(out_dir, exist_ok=True)
            free = free_space_bytes(out_dir)
            if 0 <= free < _MIN_FREE_BYTES:
                raise RuntimeError(
                    f"Only {free / 1e6:.0f} MB free on the output drive. "
                    "Choose a folder with more space."
                )

            self.log(f"Target: {cfg.target.label}")
            self.log(cfg.describe())

            self._encoder = select_encoder(force_cpu=cfg.force_cpu, log=self.log)
            self.log(
                f"Encoder: {self._encoder.label} "
                f"({self._encoder.tier_name(cfg.demand_fps)} preset)"
            )

            session = CaptureSession(
                cfg.target,
                cursor_capture=cfg.cursor_capture,
                draw_border=cfg.draw_border or None,
                minimum_update_interval_ms=suggest_update_interval_ms(cfg.sample_period),
            )
            session.start()
            self._session = session
            for warning in session.warnings:
                self.log(warning)

            if not session.wait_for_first_frame(8.0):
                raise RuntimeError(
                    "No frame arrived from the capture source within 8 seconds. "
                    "If the window is minimised, restore it and try again."
                )

            first, _ = session.latest()
            if first is None:
                raise RuntimeError("Capture produced no frame")

            self._out_size = _resolve_output_size(cfg.resolution, first.shape)
            width, height = self._out_size
            self.log(
                f"Source {first.shape[1]}x{first.shape[0]} -> output {width}x{height}"
            )

            self._writer = FFmpegWriter(
                cfg.output_path,
                width,
                height,
                cfg.output_fps,
                self._encoder,
                demand_fps=cfg.demand_fps,
            )

            self._started_at = time.perf_counter()
            self._set_state("recording")

            self._writer_thread = threading.Thread(
                target=self._write_loop, daemon=True, name="tl-writer"
            )
            self._writer_thread.start()
            self._sampler = threading.Thread(
                target=self._sample_loop, daemon=True, name="tl-sampler"
            )
            self._sampler.start()
            self.log("Recording started")
        except Exception as exc:
            self._error = str(exc)
            self._set_state("error")
            self.log(f"ERROR: {exc}")
            self._cleanup_after_failure()

    def _cleanup_after_failure(self) -> None:
        if self._session is not None:
            try:
                self._session.stop()
            except Exception:
                pass
        if self._writer is not None:
            try:
                self._writer.abort()
            except Exception:
                pass

    def _sample_loop(self) -> None:
        """Emit exactly one frame per sample period, on an absolute clock.

        Deadlines advance by a fixed step instead of sleeping a fixed amount, so
        scheduling jitter or a slow scale never accumulates into drift. When the
        source has not redrawn, the previous frame is re-emitted, which is what
        keeps the output at a genuinely constant frame rate.
        """
        cfg = self.config
        session = self._session
        assert session is not None
        period = cfg.sample_period
        width, height = self._out_size
        scaler = _Letterboxer(width, height)

        last_sequence = -1
        last_output: np.ndarray | None = None

        # Raising the system timer resolution matters even with a high-resolution
        # waitable timer, because it also tightens general thread scheduling.
        with TimerResolution(1):
            next_deadline = time.perf_counter()
            while not self._stop_event.is_set():
                frame, sequence = session.latest()
                if frame is not None and sequence != last_sequence:
                    last_sequence = sequence
                    last_output = scaler(frame)

                if last_output is not None:
                    self._enqueue(last_output)

                if session.is_closed:
                    self.log("Capture source closed; finishing up")
                    break

                next_deadline += period
                delay = next_deadline - time.perf_counter()
                if delay < -period:
                    # Fell far behind (e.g. the machine slept); resync instead of
                    # bursting out a pile of catch-up frames.
                    next_deadline = time.perf_counter()
                    delay = 0.0
                if self._waiter.wait(delay):
                    break

        self._frames.put(_STOP)
        if not self._stop_event.is_set():
            # The source closed or the writer failed rather than the user
            # pressing Stop, so finalise the file on our own.
            self.stop()

    def _enqueue(self, frame: np.ndarray) -> None:
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            # Encoder is behind. Drop the oldest frame so the recording keeps
            # real-time pace instead of ballooning memory.
            try:
                self._frames.get_nowait()
                self._frames_dropped += 1
            except queue.Empty:
                pass
            try:
                self._frames.put_nowait(frame)
            except queue.Full:
                self._frames_dropped += 1

    def _write_loop(self) -> None:
        writer = self._writer
        assert writer is not None
        try:
            while True:
                item = self._frames.get()
                if item is _STOP:
                    break
                writer.write(item)
        except Exception as exc:
            self._error = str(exc)
            self.log(f"ERROR: {exc}")
            self._set_state("error")
            # Stop sampling; there is nothing left to write to.
            self._stop_event.set()
            self._waiter.cancel()

    def stop(self) -> None:
        if self.state not in ("recording", "starting"):
            return
        self._set_state("stopping")
        threading.Thread(target=self._shutdown, daemon=True, name="tl-stop").start()

    def _shutdown(self) -> None:
        self._stop_event.set()
        self._waiter.cancel()
        if self._sampler is not None:
            self._sampler.join(timeout=10)
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=120)
        if self._session is not None:
            self._session.stop()

        writer = self._writer
        if writer is not None:
            if writer.frames_written == 0:
                writer.abort()
                self._error = self._error or "No frames were captured"
                self._set_state("error")
                self.log("ERROR: no frames were captured, nothing was written")
                return
            self.log("Finalising video...")
            writer.close()
            if writer.returncode not in (0, None):
                self._error = writer.stderr_tail or f"ffmpeg exited {writer.returncode}"
                self._set_state("error")
                self.log(f"ERROR: {self._error}")
                return

        self._finished_at = time.perf_counter()
        self._waiter.close()
        if self.state != "error":
            self._set_state("finished")
            self.log(f"Saved {self.config.output_path}")

    def latest_frame(self) -> np.ndarray | None:
        """Most recent captured frame, used for the live preview while recording."""
        session = self._session
        if session is None:
            return None
        frame, _ = session.latest()
        return frame

    def snapshot(self) -> RecordingStats:
        cfg = self.config
        writer = self._writer
        session = self._session
        state = self.state

        if self._started_at:
            end = self._finished_at if self._finished_at else time.perf_counter()
            elapsed = end - self._started_at
        else:
            elapsed = 0.0

        frames_written = writer.frames_written if writer else 0
        try:
            size = os.path.getsize(cfg.output_path)
        except OSError:
            size = 0

        stats = RecordingStats(
            state=state,
            elapsed_s=elapsed,
            frames_written=frames_written,
            frames_dropped=self._frames_dropped,
            source_frames=session.stats.frames_received if session else 0,
            output_bytes=size,
            encoder_label=self._encoder.label if self._encoder else "",
            resolution=self._out_size,
            error=self._error,
            output_path=cfg.output_path,
        )
        stats._video_seconds = frames_written / cfg.output_fps
        return stats


class _Letterboxer:
    """Fits any source frame into a fixed canvas, preserving aspect ratio.

    The canvas size is locked for the whole recording, so resizing the captured
    window mid-take changes the letterboxing rather than breaking the stream.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._last_src: tuple[int, int] | None = None
        self._plan: tuple[int, int, int, int] | None = None

    def _compute(self, src_w: int, src_h: int) -> tuple[int, int, int, int]:
        scale = min(self.width / src_w, self.height / src_h)
        new_w = max(2, int(round(src_w * scale)) & ~1)
        new_h = max(2, int(round(src_h * scale)) & ~1)
        return new_w, new_h, (self.width - new_w) // 2, (self.height - new_h) // 2

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        src_h, src_w = frame.shape[:2]
        if (src_w, src_h) == (self.width, self.height):
            return frame  # already the target size, pass through untouched

        if (src_w, src_h) != self._last_src:
            self._last_src = (src_w, src_h)
            self._plan = self._compute(src_w, src_h)
        new_w, new_h, off_x, off_y = self._plan

        # INTER_AREA is the right filter for downscaling; it averages the pixels
        # being discarded instead of point-sampling them, which is what keeps
        # small text legible in a shrunken capture.
        interp = cv2.INTER_AREA if new_w < src_w else cv2.INTER_CUBIC
        resized = cv2.resize(frame, (new_w, new_h), interpolation=interp)

        if new_w == self.width and new_h == self.height:
            return np.ascontiguousarray(resized)

        canvas = np.zeros((self.height, self.width, 3), np.uint8)
        canvas[off_y : off_y + new_h, off_x : off_x + new_w] = resized
        return canvas


def _resolve_output_size(
    requested: tuple[int, int] | None, source_shape: tuple[int, ...]
) -> tuple[int, int]:
    if requested is not None:
        return requested
    # h264 requires even dimensions in yuv420p.
    height, width = source_shape[0], source_shape[1]
    return (max(2, width & ~1), max(2, height & ~1))


def suggest_filename(target: CaptureTarget, mode: str) -> str:
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    label = "".join(
        ch if ch.isalnum() or ch in "-_" else "-" for ch in target.label.split(" - ")[0]
    ).strip("-")
    label = label or "capture"
    tag = {MODE_REALTIME: "realtime", MODE_INTERVAL: "interval"}.get(mode, "timelapse")
    return f"{label}-{tag}-{stamp}.mp4"
