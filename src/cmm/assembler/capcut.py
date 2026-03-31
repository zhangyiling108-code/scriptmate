from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import httpx

from cmm.assembler.base import BaseAssembler
from cmm.config import CapCutSettings
from cmm.models import AnalysisResult, DraftResult, MatchedSegment, VideoSource, model_dump_compat


class CapCutAssembler(BaseAssembler):
    def __init__(self, settings: CapCutSettings):
        self.settings = settings

    async def build(
        self,
        matched_segments: List[MatchedSegment],
        analysis: AnalysisResult,
        output_dir: str,
        source_video: Optional[VideoSource] = None,
    ) -> DraftResult:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = target_dir / "draft_manifest.json"
        timeline = []
        tracks = {"placeholders": [], "visuals": [], "captions": [], "talking_head_base": []}
        current_time = 0.0
        total_duration = sum(matched.segment.duration_hint for matched in matched_segments)
        if source_video:
            tracks["talking_head_base"].append(
                {
                    "asset": model_dump_compat(source_video),
                    "start": 0.0,
                    "end": round(source_video.duration or total_duration, 2),
                    "kind": "primary_talking_head_video",
                }
            )
        for matched in matched_segments:
            active_asset = matched.primary
            if matched.segment.scene_type == "talking_head" and source_video:
                active_asset = {
                    "source_type": "talking_head_video",
                    "media_type": "video",
                    "uri": source_video.path,
                    "duration": source_video.duration,
                    "width": source_video.width,
                    "height": source_video.height,
                    "has_audio": source_video.has_audio,
                }
            entry = {
                "segment_id": matched.segment.id,
                "scene_type": matched.segment.scene_type,
                "start": current_time,
                "duration": matched.segment.duration_hint,
                "end": round(current_time + matched.segment.duration_hint, 2),
                "asset": model_dump_compat(active_asset) if active_asset else None,
                "placeholder_only": matched.segment.scene_type == "talking_head" and source_video is None,
                "text": matched.segment.text,
            }
            timeline.append(entry)
            tracks["captions"].append(
                {
                    "segment_id": matched.segment.id,
                    "start": current_time,
                    "end": round(current_time + matched.segment.duration_hint, 2),
                    "text": matched.segment.text,
                }
            )
            if matched.segment.scene_type == "talking_head":
                if source_video:
                    tracks["visuals"].append(
                        {
                            "segment_id": matched.segment.id,
                            "start": current_time,
                            "end": round(current_time + matched.segment.duration_hint, 2),
                            "asset": model_dump_compat(active_asset),
                            "kind": "talking_head_source",
                        }
                    )
                else:
                    tracks["placeholders"].append(
                        {
                            "segment_id": matched.segment.id,
                            "start": current_time,
                            "end": round(current_time + matched.segment.duration_hint, 2),
                            "kind": "talking_head_slot",
                        }
                    )
            elif matched.primary:
                tracks["visuals"].append(
                    {
                        "segment_id": matched.segment.id,
                        "start": current_time,
                        "end": round(current_time + matched.segment.duration_hint, 2),
                        "asset": model_dump_compat(matched.primary),
                    }
                )
            current_time += matched.segment.duration_hint
        payload = {
            "analysis": model_dump_compat(analysis),
            "timeline": timeline,
            "tracks": tracks,
            "capcut_request": {
                "meta": {
                    "aspect": analysis.target_aspect,
                    "total_duration": round(source_video.duration or current_time, 2) if source_video else round(current_time, 2),
                },
                "tracks": tracks,
            },
        }
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        reachable, message = await self._healthcheck()
        if not reachable:
            return DraftResult(
                success=False,
                draft_dir=str(target_dir),
                manifest_path=str(manifest_path),
                message="capcut-mate unavailable: {0}".format(message),
            )
        return DraftResult(
            success=True,
            draft_dir=str(target_dir),
            manifest_path=str(manifest_path),
            message="Draft manifest prepared for capcut-mate integration.",
        )

    async def _healthcheck(self):
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(self.settings.base_url.rstrip("/") + "/health")
                if response.status_code < 500:
                    return True, "ok"
        except Exception as exc:
            return False, str(exc)
        return False, "unexpected status"
