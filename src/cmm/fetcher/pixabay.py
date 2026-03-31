from __future__ import annotations

import asyncio
from typing import List

from cmm.config import MatchingSettings
from cmm.fetcher.base import BaseStockProvider
from cmm.models import MaterialCandidate, Segment
from cmm.utils.http import build_async_client
from cmm.utils.retry import with_retry


class PixabayProvider(BaseStockProvider):
    def __init__(self, api_key: str, matching: MatchingSettings):
        self.api_key = api_key
        self.matching = matching

    async def search(self, segment: Segment, query: str) -> List[MaterialCandidate]:
        if not self.api_key:
            return []
        tasks = [self._search_videos(query, segment)]
        if segment.scene_type == "infographic":
            tasks.append(self._search_images(query))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: List[MaterialCandidate] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            merged.extend(result)
        return merged

    async def _search_videos(self, query: str, segment: Segment) -> List[MaterialCandidate]:
        async def _request():
            async with build_async_client() as client:
                response = await client.get(
                    "https://pixabay.com/api/videos/",
                    params={"key": self.api_key, "q": query, "per_page": 3},
                )
                response.raise_for_status()
                return response.json()

        payload = await with_retry(_request)
        results = []
        for item in payload.get("hits", []):
            videos = item.get("videos", {})
            best = _select_video_variant(videos, self.matching)
            if not best:
                continue
            duration = item.get("duration")
            resolution_fit = _resolution_fit(best.get("width") or 0, best.get("height") or 0, self.matching.video_min_resolution)
            results.append(
                MaterialCandidate(
                    id="pixabay:{0}".format(item["id"]),
                    source_type="pixabay",
                    media_type="video",
                    uri=best["url"],
                    thumbnail_url=item.get("videos", {}).get("tiny", {}).get("thumbnail") or "",
                    preview_uri=item.get("videos", {}).get("tiny", {}).get("thumbnail") or best["url"],
                    source_page=item.get("pageURL", ""),
                    relevance_score=0.0,
                    match_level="generic",
                    license_type="pixabay",
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
                    provider_meta={"query": query, "user": item.get("user", ""), "kind": "video", "title": item.get("tags", "")},
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

    async def _search_images(self, query: str) -> List[MaterialCandidate]:
        async def _request():
            async with build_async_client() as client:
                response = await client.get(
                    "https://pixabay.com/api/",
                    params={"key": self.api_key, "q": query, "per_page": 3, "image_type": "photo"},
                )
                response.raise_for_status()
                return response.json()

        payload = await with_retry(_request)
        results = []
        for item in payload.get("hits", []):
            image_url = item.get("largeImageURL") or item.get("webformatURL")
            if not image_url:
                continue
            results.append(
                MaterialCandidate(
                    id="pixabay-image:{0}".format(item["id"]),
                    source_type="pixabay",
                    media_type="image",
                    uri=image_url,
                    thumbnail_url=item.get("previewURL") or item.get("webformatURL") or image_url,
                    preview_uri=item.get("previewURL") or item.get("webformatURL") or image_url,
                    source_page=item.get("pageURL", ""),
                    relevance_score=0.0,
                    match_level="generic",
                    license_type="pixabay",
                    attribution_required=False,
                    width=item.get("imageWidth"),
                    height=item.get("imageHeight"),
                    tags=[query],
                    quality_signals={
                        "hd": (item.get("imageHeight") or 0) >= 1080,
                        "orientation": "vertical" if (item.get("imageHeight") or 0) >= (item.get("imageWidth") or 0) else "horizontal",
                        "resolution_fit": _resolution_fit(item.get("imageWidth") or 0, item.get("imageHeight") or 0, self.matching.video_min_resolution),
                    },
                    provider_meta={"query": query, "user": item.get("user", ""), "kind": "image", "title": item.get("tags", "")},
                )
            )
        return results


def _select_video_variant(videos, matching: MatchingSettings):
    variants = [videos.get(name) for name in ("small", "medium", "large")]
    variants = [variant for variant in variants if variant]
    if not variants:
        return None

    def qualifies(variant):
        width = variant.get("width") or 0
        height = variant.get("height") or 0
        if min(width, height) < matching.video_min_resolution:
            return False
        if not _orientation_accepts(width, height, matching.video_orientation):
            return False
        return True

    eligible = [variant for variant in variants if qualifies(variant)]
    acceptable_floor = [
        variant
        for variant in variants
        if min(variant.get("width") or 0, variant.get("height") or 0) >= 720
        and _orientation_accepts(variant.get("width") or 0, variant.get("height") or 0, matching.video_orientation)
    ]
    pool = eligible or acceptable_floor or variants
    return min(
        pool,
        key=lambda variant: (
            _resolution_penalty(variant.get("width") or 0, variant.get("height") or 0, matching.video_min_resolution),
            _orientation_penalty(variant.get("width") or 0, variant.get("height") or 0, matching.video_orientation),
            (variant.get("width") or 0) * (variant.get("height") or 0),
            variant.get("height") or 0,
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
