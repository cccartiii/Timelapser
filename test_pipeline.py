"""Headless end-to-end check of the recording pipeline.

Records a real capture target in each mode and verifies the resulting MP4 has
the expected resolution, frame rate and duration. All output goes to E:.
"""

from __future__ import annotations

import os
import re
import sys
import time

from timelapser import encoder
from timelapser.pipeline import (
    MODE_INTERVAL,
    MODE_REALTIME,
    MODE_SPEED,
    Recorder,
    RecordingConfig,
)
from timelapser.winenum import list_targets

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".testout")


def drain(recorder: Recorder, prefix: str = "    ") -> None:
    while not recorder.logs.empty():
        print(prefix + recorder.logs.get())


def parse_media(path: str) -> dict:
    info = encoder.probe_media(path)
    result = {"raw": info}
    duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    if duration:
        h, m, s = duration.groups()
        result["duration"] = int(h) * 3600 + int(m) * 60 + float(s)
    size = re.search(r", (\d+)x(\d+)", info)
    if size:
        result["size"] = (int(size.group(1)), int(size.group(2)))
    fps = re.search(r"([\d.]+) fps", info)
    if fps:
        result["fps"] = float(fps.group(1))
    return result


def run_case(name: str, config: RecordingConfig, record_seconds: float) -> bool:
    print(f"\n=== {name}")
    print(f"    {config.describe()}")
    recorder = Recorder(config)
    recorder.start()

    deadline = time.time() + 20
    while recorder.state in ("idle", "starting") and time.time() < deadline:
        drain(recorder)
        time.sleep(0.1)
    drain(recorder)
    if recorder.state != "recording":
        print(f"    FAILED to start (state={recorder.state})")
        return False

    time.sleep(record_seconds)
    recorder.stop()

    deadline = time.time() + 180
    while recorder.state == "stopping" and time.time() < deadline:
        drain(recorder)
        time.sleep(0.2)
    drain(recorder)

    stats = recorder.snapshot()
    if stats.state != "finished":
        print(f"    FAILED (state={stats.state}) {stats.error}")
        return False

    media = parse_media(config.output_path)
    expected_frames = record_seconds / config.sample_period
    print(
        f"    wrote {stats.frames_written} frames "
        f"(expected ~{expected_frames:.0f}), dropped {stats.frames_dropped}, "
        f"source frames {stats.source_frames}"
    )
    print(
        f"    file {stats.output_bytes / 1024:.0f} KB | "
        f"{media.get('size')} @ {media.get('fps')} fps | "
        f"duration {media.get('duration')}s"
    )

    ok = True
    if media.get("size") != config.resolution and config.resolution is not None:
        print(f"    MISMATCH resolution {media.get('size')} != {config.resolution}")
        ok = False
    if media.get("fps") != float(config.output_fps):
        print(f"    MISMATCH fps {media.get('fps')} != {config.output_fps}")
        ok = False
    # Frame count should track wall-clock time within one sample period plus a
    # little slack for startup.
    tolerance = max(2.0, expected_frames * 0.15)
    if abs(stats.frames_written - expected_frames) > tolerance:
        print(
            f"    MISMATCH frame count {stats.frames_written} vs "
            f"~{expected_frames:.0f} (tolerance {tolerance:.0f})"
        )
        ok = False
    print("    OK" if ok else "    PROBLEMS FOUND")
    return ok


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    targets = list_targets()
    if not targets:
        print("no capture targets found")
        return 1
    target = targets[0]
    windows = [t for t in targets if not t.is_monitor]
    window = windows[0] if windows else None
    print(f"Using monitor target: {target}")
    print(f"Using window target:  {window}")

    cases = [
        (
            "Timelapse - speed multiplier 10x at 60fps",
            RecordingConfig(
                target=target,
                output_path=os.path.join(OUT_DIR, "case-speed.mp4"),
                mode=MODE_SPEED,
                speed=10.0,
                output_fps=60,
                resolution=(1920, 1080),
            ),
            10.0,
        ),
        (
            "Timelapse - 1 frame every 0.5s at 30fps",
            RecordingConfig(
                target=target,
                output_path=os.path.join(OUT_DIR, "case-interval.mp4"),
                mode=MODE_INTERVAL,
                interval_s=0.5,
                output_fps=30,
                resolution=(1280, 720),
            ),
            10.0,
        ),
        (
            "Realtime 1x at 60fps 1080p",
            RecordingConfig(
                target=target,
                output_path=os.path.join(OUT_DIR, "case-realtime.mp4"),
                mode=MODE_REALTIME,
                output_fps=60,
                resolution=(1920, 1080),
            ),
            8.0,
        ),
    ]

    if window is not None:
        cases.append(
            (
                f"Window capture, letterboxed - {window.label}",
                RecordingConfig(
                    target=window,
                    output_path=os.path.join(OUT_DIR, "case-window.mp4"),
                    mode=MODE_SPEED,
                    speed=5.0,
                    output_fps=30,
                    resolution=(1920, 1080),
                ),
                8.0,
            )
        )
        cases.append(
            (
                f"Window capture, native resolution - {window.label}",
                RecordingConfig(
                    target=window,
                    output_path=os.path.join(OUT_DIR, "case-native.mp4"),
                    mode=MODE_SPEED,
                    speed=5.0,
                    output_fps=30,
                    resolution=None,
                ),
                8.0,
            )
        )

    results = [run_case(name, cfg, secs) for name, cfg, secs in cases]

    print("\n=== summary")
    for (name, cfg, _), ok in zip(cases, results):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        try:
            os.remove(cfg.output_path)
        except OSError:
            pass
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
