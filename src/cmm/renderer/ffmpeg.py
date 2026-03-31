from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Tuple

from cmm.models import AnalysisResult, MatchedSegment, RenderResult, VideoSource


class FFmpegRenderer:
    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = ffmpeg_bin

    async def render(
        self,
        matched_segments: list[MatchedSegment],
        analysis: AnalysisResult,
        output_dir: str,
        source_video: Optional[VideoSource] = None,
    ) -> RenderResult:
        target_dir = Path(output_dir)
        clips_dir = target_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / "final.mp4"
        concat_path = target_dir / "concat.txt"
        visual_path = target_dir / "visual_track.mp4"

        width, height = _render_size(analysis.target_aspect)
        clip_paths = []
        current_time = 0.0
        for matched in matched_segments:
            clip_path = clips_dir / "segment-{0:02d}.mp4".format(matched.segment.id)
            self._render_segment_clip(
                matched=matched,
                output_path=clip_path,
                width=width,
                height=height,
                start_time=current_time,
                source_video=source_video,
            )
            clip_paths.append(clip_path)
            current_time += matched.segment.duration_hint

        concat_path.write_text(
            "\n".join("file '{0}'".format(path.resolve().as_posix().replace("'", "'\\''")) for path in clip_paths),
            encoding="utf-8",
        )
        self._run(
            [
                self.ffmpeg_bin,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-c",
                "copy",
                str(visual_path),
            ]
        )

        total_duration = round(sum(item.segment.duration_hint for item in matched_segments), 2)
        if source_video and source_video.has_audio:
            self._run(
                [
                    self.ffmpeg_bin,
                    "-y",
                    "-i",
                    str(visual_path),
                    "-ss",
                    "0",
                    "-t",
                    str(total_duration),
                    "-i",
                    source_video.path,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(final_path),
                ]
            )
        else:
            self._run(
                [
                    self.ffmpeg_bin,
                    "-y",
                    "-i",
                    str(visual_path),
                    "-c",
                    "copy",
                    str(final_path),
                ]
            )

        return RenderResult(success=True, output_path=str(final_path), message="Rendered final mp4 with ffmpeg.")

    def _render_segment_clip(
        self,
        matched: MatchedSegment,
        output_path: Path,
        width: int,
        height: int,
        start_time: float,
        source_video: Optional[VideoSource],
    ) -> None:
        duration = round(max(0.2, matched.segment.duration_hint), 2)
        vf = "scale={0}:{1}:force_original_aspect_ratio=decrease,pad={0}:{1}:(ow-iw)/2:(oh-ih)/2:black,fps=25,format=yuv420p".format(width, height)

        if matched.segment.scene_type == "talking_head" and source_video:
            self._run(
                [
                    self.ffmpeg_bin,
                    "-y",
                    "-ss",
                    str(round(start_time, 2)),
                    "-t",
                    str(duration),
                    "-i",
                    source_video.path,
                    "-vf",
                    vf,
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    str(output_path),
                ]
            )
            return

        asset_path = _resolve_asset_path(matched)
        if asset_path and asset_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            self._run(
                [
                    self.ffmpeg_bin,
                    "-y",
                    "-loop",
                    "1",
                    "-t",
                    str(duration),
                    "-i",
                    str(asset_path),
                    "-vf",
                    vf,
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    str(output_path),
                ]
            )
            return

        if asset_path and asset_path.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}:
            self._run(
                [
                    self.ffmpeg_bin,
                    "-y",
                    "-t",
                    str(duration),
                    "-i",
                    str(asset_path),
                    "-vf",
                    vf,
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    str(output_path),
                ]
            )
            return

        self._run(
            [
                self.ffmpeg_bin,
                "-y",
                "-f",
                "lavfi",
                "-t",
                str(duration),
                "-i",
                "color=c=black:s={0}x{1}:r=25".format(width, height),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )

    def _run(self, command: list[str]) -> None:
        subprocess.run(command, check=True, capture_output=True, text=True)


def _render_size(aspect: str) -> Tuple[int, int]:
    mapping = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
    }
    return mapping.get(aspect, (1080, 1920))


def _resolve_asset_path(matched: MatchedSegment) -> Optional[Path]:
    if matched.primary is None:
        return None
    downloaded = matched.primary.provider_meta.get("downloaded_path")
    if downloaded:
        path = Path(downloaded)
        if path.exists():
            return path
    path = Path(matched.primary.uri)
    if path.exists():
        return path
    return None
