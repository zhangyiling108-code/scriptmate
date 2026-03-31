from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from cmm.models import VideoSource


def probe_video(path: str) -> VideoSource:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError("Video file not found: {0}".format(target))

    payload = _ffprobe(target)
    if not payload:
        return VideoSource(path=str(target))

    streams = payload.get("streams", [])
    format_info = payload.get("format", {})
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    duration = _to_float(format_info.get("duration")) or _to_float(video_stream.get("duration"))
    width = _to_int(video_stream.get("width"))
    height = _to_int(video_stream.get("height"))
    return VideoSource(
        path=str(target),
        duration=duration,
        width=width,
        height=height,
        has_audio=audio_stream is not None,
    )


def _ffprobe(path: Path) -> Optional[dict]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception:
        return None
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return None


def _to_float(value) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> Optional[int]:
    try:
        if value in ("", None):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
