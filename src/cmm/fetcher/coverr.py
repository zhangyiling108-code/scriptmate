from __future__ import annotations

from typing import List

from cmm.aspect import aspect_fit
from cmm.config import MatchingSettings
from cmm.fetcher.base import BaseStockProvider
from cmm.models import MaterialCandidate, Segment
from cmm.utils.http import build_async_client
from cmm.utils.retry import with_retry


class CoverrProvider(BaseStockProvider):
    def __init__(self, api_key: str, matching: MatchingSettings, base_url: str = ""):
        self.api_key = api_key
        self.matching = matching
        self.base_url = (base_url or "https://api.coverr.co").rstrip("/")

    async def search(self, segment: Segment, query: str) -> List[MaterialCandidate]:
        if not self.api_key:
            return []

        async def _request():
            async with build_async_client() as client:
                response = await client.get(
                    "{0}/videos".format(self.base_url),
                    headers={"Authorization": "Bearer {0}".format(self.api_key)},
                    params={
                        "query": query,
                        "page": 0,
                        "page_size": _provider_page_size(self.matching),
                        "sort": "popular",
                        "urls": "true",
                    },
                )
                response.raise_for_status()
                return response.json()

        payload = await with_retry(_request)
        results = []
        for item in payload.get("hits", []):
            candidate = _candidate_from_coverr_item(item, query, segment, self.matching)
            if candidate:
                results.append(candidate)
        return sorted(
            results,
            key=lambda item: (
                -item.quality_signals.get("resolution_fit", 0.0),
                -item.quality_signals.get("duration_fit", 0.0),
                (item.width or 0) * (item.height or 0),
            ),
        )


def _candidate_from_coverr_item(item, query: str, segment: Segment, matching: MatchingSettings):
    urls = item.get("urls") or {}
    video_url = urls.get("mp4") or urls.get("mp4_download") or urls.get("mp4_preview") or ""
    if not video_url:
        return None
    width = int(item.get("max_width") or 0) or None
    height = int(item.get("max_height") or 0) or None
    duration = _safe_float(item.get("duration"))
    title = str(item.get("title") or "")
    tags = [str(tag) for tag in item.get("tags", []) if str(tag).strip()]
    source_id = str(item.get("id") or item.get("video_id") or item.get("objectID") or title or video_url)
    orientation = "vertical" if item.get("is_vertical") else "horizontal"
    return MaterialCandidate(
        id="coverr:{0}".format(source_id),
        source_type="coverr",
        media_type="video",
        uri=video_url,
        thumbnail_url=item.get("thumbnail") or item.get("poster") or urls.get("mp4_preview") or video_url,
        preview_uri=urls.get("mp4_preview") or item.get("thumbnail") or item.get("poster") or video_url,
        source_page="https://coverr.co/videos/{0}".format(item.get("slug") or source_id),
        relevance_score=0.0,
        match_level="generic",
        license_type="coverr",
        attribution_required=True,
        duration=duration,
        width=width,
        height=height,
        tags=[query] + tags,
        quality_signals={
            "hd": (height or 0) >= 1080,
            "orientation": orientation,
            "target_aspect": matching.target_aspect,
            "aspect_fit": aspect_fit(width or 0, height or 0, matching.target_aspect),
            "duration_fit": _duration_fit(segment.duration_hint, duration),
            "resolution_fit": _resolution_fit(width or 0, height or 0, matching.video_min_resolution),
        },
        provider_meta={
            "query": query,
            "title": title,
            "description": item.get("description", ""),
            "aspect_ratio": item.get("aspect_ratio", ""),
            "is_ai_generated": bool(item.get("is_ai_generated", False)),
            "download_url": urls.get("mp4_download", ""),
        },
    )


def _provider_page_size(matching: MatchingSettings) -> int:
    return min(max(int(matching.search_pool_size or 3), 3), 80)


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _resolution_fit(width: int, height: int, requested_min: int) -> float:
    short_edge = min(width, height)
    if short_edge >= requested_min:
        return 1.0
    if short_edge >= 1080:
        return 0.82
    if short_edge >= 720:
        return 0.62
    return 0.0
