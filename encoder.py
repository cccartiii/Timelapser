"""ffmpeg discovery, hardware encoder probing, and the raw-frame writer."""

from __future__ import annotations

import collections
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field

from .paths import child_env

CREATE_NO_WINDOW = 0x08000000

_ffmpeg_path: str | None = None
_probe_cache: dict[bool, "Encoder"] = {}


# Above this many frames per second the encoder must keep up with a live capture,
# so throughput matters more than squeezing out the last few percent of bitrate.
_SPEED_TIER_FPS = 45.0
_BALANCED_TIER_FPS = 20.0


@dataclass(frozen=True)
class Encoder:
    name: str
    label: str
    quality_args: tuple[str, ...] = field(default_factory=tuple)
    balanced_args: tuple[str, ...] = field(default_factory=tuple)
    speed_args: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_hardware(self) -> bool:
        return self.name != "libx264"

    def args_for(self, demand_fps: float) -> tuple[str, ...]:
        """Preset matched to how fast frames will actually be handed over.

        A slow timelapse produces a couple of frames a second and can afford the
        best preset; 1x realtime at 60fps cannot.
        """
        if demand_fps > _SPEED_TIER_FPS:
            return self.speed_args
        if demand_fps > _BALANCED_TIER_FPS:
            return self.balanced_args
        return self.quality_args

    def tier_name(self, demand_fps: float) -> str:
        if demand_fps > _SPEED_TIER_FPS:
            return "speed"
        if demand_fps > _BALANCED_TIER_FPS:
            return "balanced"
        return "quality"


_NVENC_RC = ("-rc", "vbr", "-cq", "21", "-b:v", "0")
_AMF_RC = ("-rc", "cqp", "-qp_i", "22", "-qp_p", "22", "-qp_b", "24")

# Ordered by preference. Each entry is validated by a real trial encode before use.
CANDIDATES: tuple[Encoder, ...] = (
    Encoder(
        "h264_nvenc",
        "NVIDIA NVENC",
        quality_args=("-preset", "p6", "-tune", "hq", *_NVENC_RC),
        balanced_args=("-preset", "p4", *_NVENC_RC),
        speed_args=("-preset", "p2", *_NVENC_RC),
    ),
    Encoder(
        "h264_qsv",
        "Intel Quick Sync",
        quality_args=("-preset", "slow", "-global_quality", "22"),
        balanced_args=("-preset", "medium", "-global_quality", "22"),
        speed_args=("-preset", "veryfast", "-global_quality", "22"),
    ),
    Encoder(
        "h264_amf",
        "AMD AMF",
        quality_args=("-quality", "quality", *_AMF_RC),
        balanced_args=("-quality", "balanced", *_AMF_RC),
        speed_args=("-quality", "speed", *_AMF_RC),
    ),
)

CPU_ENCODER = Encoder(
    "libx264",
    "CPU x264",
    quality_args=("-preset", "medium", "-crf", "20"),
    balanced_args=("-preset", "veryfast", "-crf", "20"),
    speed_args=("-preset", "veryfast", "-crf", "21"),
)


def ffmpeg_exe() -> str:
    """Path to the bundled ffmpeg, preferring one shipped alongside a frozen exe."""
    global _ffmpeg_path
    if _ffmpeg_path:
        return _ffmpeg_path

    if getattr(sys, "frozen", False):
        bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "ffmpeg.exe")
        if os.path.isfile(bundled):
            _ffmpeg_path = bundled
            return _ffmpeg_path

    from imageio_ffmpeg import get_ffmpeg_exe

    _ffmpeg_path = get_ffmpeg_exe()
    return _ffmpeg_path


def _run(args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
        timeout=timeout,
        text=True,
        errors="replace",
        env=child_env(),
    )


def _listed_encoders() -> set[str]:
    try:
        result = _run([ffmpeg_exe(), "-hide_banner", "-encoders"])
    except Exception:
        return set()
    return {
        match.group(1)
        for match in re.finditer(r"^\s*V[\w.]*\s+(\S+)", result.stdout, re.MULTILINE)
    }


def _trial_encode(encoder: Encoder) -> bool:
    """Encode a few synthetic frames to confirm the hardware actually accepts it.

    Being listed by `ffmpeg -encoders` only means support was compiled in; the
    driver or GPU may still refuse at runtime.
    """
    args = [
        ffmpeg_exe(),
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", "color=c=black:s=640x360:r=30:d=0.2",
        "-c:v", encoder.name,
        *encoder.speed_args,
        "-pix_fmt", "yuv420p",
        "-f", "null",
        "-",
    ]
    try:
        return _run(args, timeout=25.0).returncode == 0
    except Exception:
        return False


def select_encoder(force_cpu: bool = False, log=None) -> Encoder:
    """Pick the best working encoder, caching the (slow) probe result."""
    if force_cpu:
        return CPU_ENCODER
    if False in _probe_cache:
        return _probe_cache[False]

    available = _listed_encoders()
    for candidate in CANDIDATES:
        if candidate.name not in available:
            continue
        if log:
            log(f"Testing {candidate.label}...")
        if _trial_encode(candidate):
            _probe_cache[False] = candidate
            return candidate
        if log:
            log(f"{candidate.label} is present but not usable; skipping")

    _probe_cache[False] = CPU_ENCODER
    return CPU_ENCODER


class FFmpegWriter:
    """Pipes raw BGR frames into ffmpeg and produces a faststart MP4."""

    def __init__(
        self,
        path: str,
        width: int,
        height: int,
        fps: int,
        encoder: Encoder,
        demand_fps: float | None = None,
    ) -> None:
        self.path = path
        self.width = width
        self.height = height
        self.fps = fps
        self.encoder = encoder
        self.demand_fps = fps if demand_fps is None else demand_fps
        self.tier = encoder.tier_name(self.demand_fps)
        self.frames_written = 0
        self._closed = False
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=40)

        args = [
            ffmpeg_exe(),
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-an",
            "-c:v", encoder.name,
            *encoder.args_for(self.demand_fps),
            # Input is already exact CFR, so let ffmpeg pass timestamps through
            # rather than second-guessing them.
            "-fps_mode", "passthrough",
            "-g", str(fps * 2),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            path,
        ]
        self.command = args

        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
            env=child_env(),
        )
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True, name="ffmpeg-stderr"
        )
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        # Must be drained continuously or a full pipe would block ffmpeg.
        stream = self._proc.stderr
        if stream is None:
            return
        for line in iter(stream.readline, b""):
            text = line.decode("utf-8", "replace").strip()
            if text:
                self._stderr_tail.append(text)
        stream.close()

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_tail)

    def write(self, frame) -> None:
        """Write one C-contiguous HxWx3 BGR frame."""
        if self._closed or self._proc.stdin is None:
            raise RuntimeError("writer is closed")
        try:
            # memoryview avoids the extra copy that tobytes() would make.
            self._proc.stdin.write(memoryview(frame).cast("B"))
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError(
                f"ffmpeg stopped accepting frames: {exc}\n{self.stderr_tail}"
            ) from exc
        self.frames_written += 1

    def close(self, timeout: float = 60.0) -> None:
        """Flush and wait for ffmpeg to finalise the container."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)
        self._stderr_thread.join(timeout=2)

    @property
    def returncode(self) -> int | None:
        return self._proc.poll()

    def abort(self) -> None:
        if not self._closed:
            self._closed = True
            self._proc.kill()
            self._proc.wait(timeout=5)


def probe_media(path: str) -> str:
    """Human-readable stream summary, used for post-recording verification."""
    try:
        result = _run([ffmpeg_exe(), "-hide_banner", "-i", path], timeout=20.0)
    except Exception as exc:
        return f"probe failed: {exc}"
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if "Duration" in line or "Stream #" in line
    ]
    return " | ".join(lines) if lines else result.stdout.strip()
