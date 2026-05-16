from __future__ import annotations

from typing import List, Optional
from urllib.parse import quote

from cmm.aspect import aspect_fit
from cmm.config import MatchingSettings
from cmm.fetcher.base import BaseStockProvider
from cmm.models import MaterialCandidate, Segment
from cmm.utils.http import build_async_client
from cmm.utils.retry import with_retry


class NasaImagesProvider(BaseStockProvider):
    def __init__(self, matching: MatchingSettings, base_url: str = ""):
        self.matching = matching
        self.base_url = (base_url or "https://images-api.nasa.gov").rstrip("/")

    async def search(self, segment: Segment, query: str) -> List[MaterialCandidate]:
        media_type = "image" if segment.visual_type == "stock_image" or segment.scene_type == "infographic" else "video"

        async def _request():
            async with build_async_client() as client:
                response = await client.get(
                    "{0}/search".format(self.base_url),
                    params={
                        "q": query,
                        "media_type": media_type,
                        "page": 1,
                        "page_size": _provider_page_size(self.matching),
                    },
                )
                response.raise_for_status()
                return response.json()

        payload = await with_retry(_request)
        items = payload.get("collection", {}).get("items", [])
        results = []
        for item in items:
            candidate = await self._candidate_from_item(item, query, segment, media_type)
            if candidate:
                results.append(candidate)
        return results

    async def _candidate_from_item(self, item, query: str, segment: Segment, requested_media_type: str) -> Optional[MaterialCandidate]:
        metadata = (item.get("data") or [{}])[0]
        nasa_id = str(metadata.get("nasa_id") or "")
        media_type = str(metadata.get("media_type") or requested_media_type)
        if media_type not in {"image", "video"}:
            return None
        if media_type == "video":
            media_url = await self._video_url(nasa_id)
            thumb = _best_image_link(item.get("links", []))
            width, height = _infer_video_dimensions(thumb)
        else:
            image = _best_image_link(item.get("links", []), prefer_canonical=True)
            media_url = image.get("href", "")
            width = image.get("width")
            height = image.get("height")
            thumb = _best_image_link(item.get("links", []))
        if not media_url:
            return None
        tags = [str(tag) for tag in metadata.get("keywords", []) if str(tag).strip()]
        title = str(metadata.get("title") or "")
        description = str(metadata.get("description") or "")
        return MaterialCandidate(
            id="nasa:{0}".format(nasa_id or media_url),
            source_type="nasa",
            media_type=media_type,
            uri=_https(media_url),
            thumbnail_url=_https(thumb.get("href", "")),
            preview_uri=_https(thumb.get("href", "") or media_url),
            source_page="https://images.nasa.gov/details/{0}".format(quote(nasa_id)) if nasa_id else item.get("href", ""),
            relevance_score=0.0,
            match_level="generic",
            license_type="nasa-media",
            attribution_required=True,
            width=width,
            height=height,
            tags=[query] + tags,
            quality_signals={
                "hd": (height or 0) >= 1080,
                "orientation": _orientation(width or 0, height or 0),
                "target_aspect": self.matching.target_aspect,
                "aspect_fit": aspect_fit(width or 0, height or 0, self.matching.target_aspect),
                "duration_fit": 0.0,
                "resolution_fit": _resolution_fit(width or 0, height or 0, self.matching.video_min_resolution),
            },
            provider_meta={
                "query": query,
                "title": title,
                "description": description,
                "center": metadata.get("center", ""),
                "date_created": metadata.get("date_created", ""),
                "nasa_id": nasa_id,
            },
        )

    async def _video_url(self, nasa_id: str) -> str:
        if not nasa_id:
            return ""

        async def _request():
            async with build_async_client() as client:
                response = await client.get("{0}/asset/{1}".format(self.base_url, quote(nasa_id)))
                response.raise_for_status()
                return response.json()

        try:
            payload = await with_retry(_request)
        except Exception:
            return ""
        hrefs = [str(item.get("href") or "") for item in payload.get("collection", {}).get("items", [])]
        return _pick_video_href(hrefs)


def _best_image_link(links, prefer_canonical: bool = False):
    image_links = [link for link in links or [] if link.get("render") == "image" and link.get("href")]
    if not image_links:
        return {}
    if prefer_canonical:
        canonical = [link for link in image_links if link.get("rel") == "canonical" or "~orig" in str(link.get("href", ""))]
        if canonical:
            return max(canonical, key=lambda link: (link.get("width") or 0) * (link.get("height") or 0))
    preview = [link for link in image_links if link.get("rel") == "preview"]
    if preview:
        return preview[0]
    return max(image_links, key=lambda link: (link.get("width") or 0) * (link.get("height") or 0))


def _pick_video_href(hrefs: List[str]) -> str:
    videos = [href for href in hrefs if href.lower().endswith((".mp4", ".mov", ".m4v"))]
    if not videos:
        return ""
    preferred_order = ("~medium.mp4", "~small.mp4", "~mobile.mp4", "~preview.mp4", ".mp4", ".mov")
    for suffix in preferred_order:
        for href in videos:
            if href.lower().endswith(suffix):
                return href
    return videos[0]


def _infer_video_dimensions(thumb) -> tuple[Optional[int], Optional[int]]:
    width = int(thumb.get("width") or 0) if thumb else 0
    height = int(thumb.get("height") or 0) if thumb else 0
    if width <= 0 or height <= 0:
        return None, None
    if width >= height:
        scaled_width = 1920
        scaled_height = max(1, round(scaled_width * height / width))
        return scaled_width, scaled_height
    scaled_height = 1920
    scaled_width = max(1, round(scaled_height * width / height))
    return scaled_width, scaled_height


def _provider_page_size(matching: MatchingSettings) -> int:
    return min(max(int(matching.search_pool_size or 3), 3), 20)


def _https(url: str) -> str:
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def _orientation(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return ""
    if width == height:
        return "square"
    return "vertical" if height > width else "horizontal"


def _resolution_fit(width: int, height: int, requested_min: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    short_edge = min(width, height)
    if short_edge >= requested_min:
        return 1.0
    if short_edge >= 1080:
        return 0.82
    if short_edge >= 720:
        return 0.62
    return 0.0
