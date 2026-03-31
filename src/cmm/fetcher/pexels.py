from __future__ import annotations

from typing import List

from cmm.config import MatchingSettings
from cmm.fetcher.base import BaseStockProvider
from cmm.models import MaterialCandidate, Segment
from cmm.utils.http import build_async_client
from cmm.utils.retry import with_retry


class PexelsProvider(BaseStockProvider):
    def __init__(self, api_key: str, matching: MatchingSettings):
        self.api_key = api_key
        self.matching = matching

    async def search(self, segment: Segment, query: str) -> List[MaterialCandidate]:
        if not self.api_key:
            return []

        async def _request():
            async with build_async_client() as client:
                response = await client.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": self.api_key},
                    params={"query": query, "per_page": 3},
                )
                response.raise_for_status()
                return response.json()

        payload = await with_retry(_request)
        results = []
        for item in payload.get("videos", []):
            files = item.get("video_files", [])
            best = _select_video_file(files, self.matching)
            if not best:
                continue
            image_url = item.get("image") or best.get("link", "")
            duration = item.get("duration")
            resolution_fit = _resolution_fit(best.get("width") or 0, best.get("height") or 0, self.matching.video_min_resolution)
            results.append(
                MaterialCandidate(
                    id="pexels:{0}".format(item["id"]),
                    source_type="pexels",
                    media_type="video",
                    uri=best["link"],
                    thumbnail_url=image_url,
                    preview_uri=image_url or best["link"],
                    source_page=item.get("url", ""),
                    relevance_score=0.0,
                    match_level="generic",
                    license_type="pexels",
                    attribution_required=False,
                    duration=duration,
                    width=best.get("width"),
                    height=best.get("height"),
                    tags=[query],
                    quality_signals={
                        "hd": (best.get("height") or 0) >= 1080,
                        "orientation": "vertical" if (best.get("height") or 0) >= (best.get("width") or 0) else "horizontal",
                        "duration_fit": _duration_fit(segment.duration_hint, duration),
                        "resolution_fit": resolution_fit,
                    },
                    provider_meta={
                        "query": query,
                        "user": item.get("user", {}).get("name", ""),
                        "title": item.get("url", ""),
                    },
                )
            )
        return sorted(
            results,
            key=lambda item: (
                -item.quality_signals.get("resolution_fit", 0.0),
                -item.quality_signals.get("duration_fit", 0.0),
                (item.width or 0) * (item.height or 0),
            ),
        )


def _select_video_file(files, matching: MatchingSettings):
    if not files:
        return None

    def qualifies(video_file):
        width = video_file.get("width") or 0
        height = video_file.get("height") or 0
        if min(width, height) < matching.video_min_resolution:
            return False
        if not _orientation_accepts(width, height, matching.video_orientation):
            return False
        return True

    eligible = [video_file for video_file in files if qualifies(video_file)]
    acceptable_floor = [
        video_file
        for video_file in files
        if min(video_file.get("width") or 0, video_file.get("height") or 0) >= 720
        and _orientation_accepts(video_file.get("width") or 0, video_file.get("height") or 0, matching.video_orientation)
    ]
    pool = eligible or acceptable_floor or files
    return min(
        pool,
        key=lambda video_file: (
            _resolution_penalty(video_file.get("width") or 0, video_file.get("height") or 0, matching.video_min_resolution),
            _orientation_penalty(video_file.get("width") or 0, video_file.get("height") or 0, matching.video_orientation),
            (video_file.get("width") or 0) * (video_file.get("height") or 0),
            video_file.get("height") or 0,
        ),
    )


def _orientation_accepts(width: int, height: int, orientation: str) -> bool:
    if orientation == "vertical":
        return height >= width
    if orientation == "horizontal":
        return width >= height
    if orientation == "square":
        return min(width, height) > 0 and abs(width - height) / max(width, height) <= 0.2
    return True


def _orientation_penalty(width: int, height: int, orientation: str) -> float:
    if width <= 0 or height <= 0:
        return 1.0
    if orientation == "vertical":
        return 0.0 if height >= width else 1.0
    if orientation == "horizontal":
        return 0.0 if width >= height else 1.0
    if orientation == "square":
        return abs(width - height) / max(width, height)
    return 0.0


def _resolution_penalty(width: int, height: int, requested_min: int) -> float:
    short_edge = min(width, height)
    if short_edge >= requested_min:
        return 0.0
    if short_edge >= 1080:
        return 0.2
    if short_edge >= 720:
        return 0.45
    return 1.0


def _resolution_fit(width: int, height: int, requested_min: int) -> float:
    short_edge = min(width, height)
    if short_edge >= requested_min:
        return 1.0
    if short_edge >= 1080:
        return 0.82
    if short_edge >= 720:
        return 0.62
    return 0.0


def _duration_fit(target: float, actual) -> float:
    if not actual or actual <= 0:
        return 0.0
    delta = abs(float(actual) - float(target))
    if delta <= 1.0:
        return 1.0
    if delta <= 3.0:
        return 0.85
    if delta <= 8.0:
        return 0.6
    return 0.35
