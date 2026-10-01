from __future__ import annotations

import re

from cmm.config import MatchingSettings, OpenSourceSettings
from cmm.fetcher.base import BaseStockProvider
from cmm.fetcher.open_media import attribution_text, license_code, media_url, plain_text
from cmm.models import MaterialCandidate, Segment
from cmm.utils.http import build_async_client
from cmm.utils.retry import with_retry


class CommonsProvider(BaseStockProvider):
    media_types = frozenset({"image"})
    supports_cjk = True

    def __init__(self, settings: OpenSourceSettings, matching: MatchingSettings):
        self.settings = settings
        self.matching = matching

    async def search(self, segment: Segment, query: str):
        if segment.visual_type != "stock_image":
            return []

        async def request():
            async with build_async_client() as client:
                response = await client.get(
                    self.settings.base_url,
                    params={"action": "query", "format": "json", "generator": "search", "gsrsearch": query,
                            "gsrnamespace": 6, "gsrlimit": min(self.matching.search_pool_size, 20), "prop": "imageinfo",
                            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1024},
                    headers={"User-Agent": "ScriptMate/0.1 (https://github.com/zhangyiling108-code/scriptmate)"},
                )
                response.raise_for_status()
                payload = response.json()
                if "error" in payload:
                    raise ValueError("Commons API rejected the search request")
                return payload

        payload = await with_retry(request)
        pages = payload.get("query", {}).get("pages", {})
        return [candidate for page in pages.values() if (candidate := self._candidate(page, query)) is not None]

    def _candidate(self, page, query):
        info = (page.get("imageinfo") or [{}])[0]
        if not str(info.get("mime", "")).startswith("image/"):
            return None
        metadata = info.get("extmetadata", {})

        def value(key):
            return plain_text(metadata.get(key, {}).get("value", ""))

        license_url = media_url(value("LicenseUrl"))
        code = license_code(value("LicenseShortName"), license_url)
        uri = media_url(info.get("url", ""))
        if code not in self.settings.allowed_licenses or not uri:
            return None
        title = value("ObjectName") or plain_text(page.get("title", ""))
        creator = value("Artist")
        source_page = media_url(info.get("descriptionurl", ""))
        version = re.search(r"/(\d+\.\d+)/(?:deed[^/]*)?$", license_url)
        return MaterialCandidate(
            id="commons:" + str(page["pageid"]), source_type="commons", media_type="image", uri=uri,
            thumbnail_url=media_url(info.get("thumburl", "")) or uri, preview_uri=uri, source_page=source_page,
            width=info.get("width"), height=info.get("height"), license_type=code, license_url=license_url,
            license_version=version.group(1) if version else "",
            creator=creator, attribution_required=code.startswith("by"),
            attribution=attribution_text(title, value("Attribution") or creator, value("LicenseShortName"), source_page),
            provider_meta={"title": title, "description": value("ImageDescription"), "query": query},
        )
