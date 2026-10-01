from __future__ import annotations

from cmm.config import MatchingSettings, OpenSourceSettings
from cmm.fetcher.base import BaseStockProvider
from cmm.fetcher.open_media import attribution_text, license_code, media_url, plain_text
from cmm.models import MaterialCandidate, Segment
from cmm.utils.http import build_async_client
from cmm.utils.retry import with_retry


class OpenverseProvider(BaseStockProvider):
    media_types = frozenset({"image"})
    supports_cjk = True

    def __init__(self, settings: OpenSourceSettings, matching: MatchingSettings):
        self.settings = settings
        self.matching = matching

    async def search(self, segment: Segment, query: str):
        if segment.visual_type != "stock_image":
            return []
        if not self.settings.allowed_licenses:
            return []

        async def request():
            headers = {"Authorization": "Bearer " + self.settings.api_key} if self.settings.api_key else {}
            async with build_async_client() as client:
                response = await client.get(
                    self.settings.base_url.rstrip("/") + "/images/",
                    params={"q": query, "page_size": min(self.matching.search_pool_size, 20), "license": ",".join(self.settings.allowed_licenses)},
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

        payload = await with_retry(request)
        return [candidate for item in payload.get("results", []) if (candidate := self._candidate(item, query)) is not None]

    def _candidate(self, item, query):
        code = license_code(item.get("license", ""), item.get("license_url", ""))
        uri = media_url(item.get("url", ""))
        if code not in self.settings.allowed_licenses or not uri:
            return None
        title = plain_text(item.get("title", ""))
        creator = plain_text(item.get("creator", ""))
        source_page = media_url(item.get("foreign_landing_url", ""))
        version = str(item.get("license_version") or "")
        return MaterialCandidate(
            id="openverse:" + str(item["id"]), source_type="openverse", media_type="image", uri=uri,
            thumbnail_url=media_url(item.get("thumbnail", "")), preview_uri=uri, source_page=source_page,
            width=item.get("width"), height=item.get("height"),
            tags=[plain_text(tag.get("name", "")) for tag in item.get("tags", []) if isinstance(tag, dict)],
            license_type=code, license_url=media_url(item.get("license_url", "")), license_version=version,
            creator=creator, creator_url=media_url(item.get("creator_url", "")),
            attribution=attribution_text(title, creator, code, source_page, version), attribution_required=code.startswith("by"),
            provider_meta={"title": title, "query": query, "origin_provider": item.get("provider", ""), "origin_source": item.get("source", "")},
        )
