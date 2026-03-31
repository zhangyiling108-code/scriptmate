from __future__ import annotations

from typing import Iterable, List

from cmm.models import LibraryAsset, MaterialCandidate, Segment


class LocalLibraryMatcher:
    def match(self, segment: Segment, assets: Iterable[LibraryAsset], top_k: int = 3) -> List[MaterialCandidate]:
        candidates = []
        for asset in assets:
            score = self._score(segment, asset)
            if score <= 0:
                continue
            match_level = "exact" if score >= 0.85 else "approx" if score >= 0.5 else "generic"
            candidates.append(
                MaterialCandidate(
                    id="local:{0}".format(asset.path),
                    source_type="local",
                    media_type=asset.asset_type,
                    uri=asset.path,
                    thumbnail_url=asset.path,
                    preview_uri=asset.path,
                    source_page=asset.path,
                    relevance_score=min(score, 1.0),
                    match_level=match_level,
                    license_type="owned",
                    attribution_required=False,
                    width=asset.width,
                    height=asset.height,
                    duration=asset.duration,
                    tags=asset.tags,
                    quality_signals={"local": True},
                    provider_meta={"title": asset.title, "category": asset.category},
                )
            )
        candidates.sort(key=lambda item: (item.relevance_score, item.match_level == "exact"), reverse=True)
        return candidates[:top_k]

    def _score(self, segment: Segment, asset: LibraryAsset) -> float:
        haystack = " ".join(
            [
                asset.title.lower(),
                asset.description.lower(),
                " ".join(asset.tags).lower(),
                asset.category.lower(),
                asset.path.lower(),
            ]
        )
        score = 0.0
        for keyword in list(segment.keywords_cn) + list(segment.keywords_en) + list(segment.search_queries):
            token = keyword.lower()
            if token and token in haystack:
                score += 0.35 if token in " ".join(asset.tags).lower() else 0.2
        if segment.scene_type == "b_roll" and asset.asset_type == "video":
            score += 0.15
        if segment.scene_type in ("text_card", "infographic") and asset.asset_type == "image":
            score += 0.05
        return min(score, 1.0)
