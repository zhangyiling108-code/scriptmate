from __future__ import annotations

import asyncio
import json
from typing import Dict, Iterable, List

from cmm.cache import FileCache
from cmm.config import MatchingSettings, SourcesSettings
from cmm.fetcher.fallback import FallbackManager
from cmm.fetcher.pexels import PexelsProvider
from cmm.fetcher.pixabay import PixabayProvider
from cmm.models import MaterialCandidate, SearchResult, Segment


class StockSearchService:
    def __init__(self, sources: SourcesSettings, matching: MatchingSettings, fallback_manager: FallbackManager, cache: FileCache):
        self.sources = sources
        self.matching = matching
        self.fallback_manager = fallback_manager
        self.cache = cache
        self.pexels = PexelsProvider(sources.pexels.api_key, matching)
        self.pixabay = PixabayProvider(sources.pixabay.api_key, matching)

    async def search(self, segment: Segment) -> List[MaterialCandidate]:
        if segment.visual_type in {"skip", "data_card", "text_card"}:
            return []
        queries = self._segment_queries(segment)
        raw = await self._search_queries(queries, segment)
        deduped = self._dedupe(raw)
        return self._apply_quality_filters(deduped)

    async def search_query(self, query: str, source: str = "all", top_k: int = 5) -> SearchResult:
        segment = Segment(id=1, text=query, search_queries=[query], keywords_en=[query])
        candidates = await self._search_queries([query], segment, source=source)
        return SearchResult(query=query, source=source, candidates=self._apply_quality_filters(self._dedupe(candidates))[:top_k])

    def mapped_queries(self, segment: Segment) -> List[str]:
        return self.fallback_manager.mapped_queries(segment)

    def generic_candidates(self, segment: Segment, top_k: int = 3) -> List[MaterialCandidate]:
        return self.fallback_manager.generic_candidates(segment, top_k=top_k)

    async def _search_queries(self, queries: Iterable[str], segment: Segment, source: str = "all") -> List[MaterialCandidate]:
        tasks = []
        for query in self._normalize_queries(self._expand_queries(list(queries), segment)):
            if source in {"all", "pexels"} and "pexels" in self.sources.enabled:
                tasks.append(self._cached_provider_search("pexels", query, segment))
            if source in {"all", "pixabay"} and "pixabay" in self.sources.enabled:
                tasks.append(self._cached_provider_search("pixabay", query, segment))
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: List[MaterialCandidate] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            merged.extend(result)
        return merged

    async def _cached_provider_search(self, provider: str, query: str, segment: Segment) -> List[MaterialCandidate]:
        cache_key = json.dumps(
            {
                "provider": provider,
                "query": query,
                "visual_type": segment.visual_type,
                "scene_type": segment.scene_type,
                "video_orientation": self.matching.video_orientation,
                "video_min_resolution": self.matching.video_min_resolution,
                "search_pool_size": self.matching.search_pool_size,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cached = self.cache.load_json("search", cache_key)
        if cached is not None:
            return [MaterialCandidate(**item) for item in cached]
        if provider == "pexels":
            result = await self.pexels.search(segment, query)
        else:
            result = await self.pixabay.search(segment, query)
        self.cache.save_json("search", cache_key, [item.model_dump() for item in result])
        return result

    def _normalize_queries(self, queries: List[str]) -> List[str]:
        deduped: List[str] = []
        seen = set()
        for query in queries:
            normalized = " ".join(str(query).split()).strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(normalized)
        return deduped[:8]

    def _segment_queries(self, segment: Segment) -> List[str]:
        layers = segment.search_query_layers or {}
        prioritized = (
            list(segment.search_queries)
            + layers.get("l1", [])
            + layers.get("l2", [])
            + layers.get("context", [])
            + layers.get("l3", [])
            + layers.get("l4", [])
        )
        context_variants = self._context_variants(segment)
        return self._normalize_queries(prioritized + context_variants)

    def _context_variants(self, segment: Segment) -> List[str]:
        variants: List[str] = []
        subject = " ".join(str(segment.narrative_subject or "").split()).strip()
        if subject:
            variants.append(subject)
            if segment.visual_type == "stock_video":
                variants.append("{0} real footage".format(subject))
            elif segment.visual_type == "stock_image":
                variants.append("{0} documentary image".format(subject))
        for tag in segment.context_tags[:4]:
            variants.append(tag)
        if segment.context_statement:
            variants.append(segment.context_statement)
        return variants

    def _expand_queries(self, queries: List[str], segment: Segment) -> List[str]:
        expanded = list(queries)
        text = "{0} {1} {2} {3}".format(
            segment.text,
            " ".join(segment.keywords_en),
            segment.narrative_subject,
            " ".join(segment.context_tags),
        ).lower()
        geo_modifiers = self._geo_modifiers(text)
        if geo_modifiers:
            geo_expansions = []
            for query in queries:
                normalized = " ".join(str(query).split()).strip()
                if not normalized:
                    continue
                lowered = normalized.lower()
                for geo in geo_modifiers:
                    if geo not in lowered:
                        geo_expansions.append("{0} {1}".format(geo, normalized))
                        geo_expansions.append("{0} {1}".format(normalized, geo))
            if "china" in geo_modifiers and any(
                hint in text for hint in ("高铁", "rail", "train", "bridge", "基建", "infrastructure", "highway", "expressway", "5g")
            ):
                geo_expansions.extend(
                    [
                        "china infrastructure",
                        "china urban development",
                        "china city skyline",
                    ]
                )
            expanded.extend(geo_expansions)
        return expanded

    def _geo_modifiers(self, text: str) -> List[str]:
        modifiers: List[str] = []
        geo_map = [
            ("china", ("中国", "china", "我国", "港珠澳", "高铁", "改革开放")),
            ("united states", ("美国", "united states", "usa", "openai", "anthropic", "google deepmind", "meta ai", "xai")),
            ("japan", ("日本", "japan", "tokyo", "fuji")),
            ("south korea", ("韩国", "south korea", "korea", "seoul")),
            ("europe", ("欧洲", "europe", "eu")),
        ]
        lowered = text.lower()
        for label, hints in geo_map:
            if any(hint.lower() in lowered for hint in hints):
                modifiers.append(label)
        deduped: List[str] = []
        seen = set()
        for item in modifiers:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _dedupe(self, candidates: List[MaterialCandidate]) -> List[MaterialCandidate]:
        seen = set()
        deduped = []
        for candidate in candidates:
            key = candidate.uri
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _apply_quality_filters(self, candidates: List[MaterialCandidate]) -> List[MaterialCandidate]:
        filtered: List[MaterialCandidate] = []
        for candidate in candidates:
            if candidate.media_type in {"video", "image"} and not _meets_min_resolution(
                candidate.width or 0,
                candidate.height or 0,
                self.matching.video_min_resolution,
            ):
                continue
            if candidate.media_type in {"video", "image"} and not _orientation_matches(
                candidate.width or 0,
                candidate.height or 0,
                self.matching.video_orientation,
            ):
                continue
            filtered.append(candidate)
        return filtered


def _orientation_matches(width: int, height: int, orientation: str) -> bool:
    if width <= 0 or height <= 0:
        return True
    if orientation == "vertical":
        return height >= width
    if orientation == "horizontal":
        return width >= height
    if orientation == "square":
        return abs(width - height) / max(width, height) <= 0.2
    return True


def _meets_min_resolution(width: int, height: int, minimum: int) -> bool:
    if width <= 0 or height <= 0:
        return True
    return min(width, height) >= 720
