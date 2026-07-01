from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from cmm.aspect import normalize_aspect, orientation_for_aspect
from cmm.models import LibraryAsset, MaterialCandidate, Segment


class LocalLibraryMatcher:
    def match(
        self,
        segment: Segment,
        assets: Iterable[LibraryAsset],
        top_k: int = 3,
        target_aspect: str = "",
    ) -> List[MaterialCandidate]:
        candidates = []
        for asset in assets:
            score, breakdown, notes = self._score(segment, asset, target_aspect)
            if score <= 0:
                continue
            match_level = "exact" if score >= 0.85 else "approx" if score >= 0.5 else "generic"
            quality_signals = {
                "local": True,
                "score_breakdown": breakdown,
                "score_notes": notes,
                "score_method": "local_index",
                "local_match_score": breakdown.get("local_match", 0.0),
                "technical_score": breakdown.get("technical", 0.0),
                "semantic_score": breakdown.get("semantic", 0.0),
                "aspect_fit": breakdown.get("aspect_fit", 0.0),
                "resolution_fit": breakdown.get("resolution_fit", 0.0),
                "duration_fit": breakdown.get("duration_fit", 0.0),
                "index_fingerprint": asset.fingerprint,
            }
            candidates.append(
                MaterialCandidate(
                    id="local:{0}".format(asset.relative_path or asset.path),
                    source_type="local",
                    media_type=asset.asset_type,
                    uri=asset.path,
                    thumbnail_url=asset.path if asset.asset_type == "image" else "",
                    preview_uri=asset.path,
                    source_page=asset.path,
                    relevance_score=min(score, 1.0),
                    match_level=match_level,
                    reason="Local library match: {0}".format("; ".join(notes[:3]) or "indexed metadata fit"),
                    license_type="owned",
                    attribution_required=False,
                    width=asset.width,
                    height=asset.height,
                    duration=asset.duration,
                    tags=asset.tags,
                    quality_signals=quality_signals,
                    provider_meta={
                        "title": asset.title,
                        "category": asset.category,
                        "relative_path": asset.relative_path,
                        "candidate_bucket": self._bucket(score),
                        "score_method": "local_index",
                    },
                )
            )
        candidates.sort(key=lambda item: (item.relevance_score, item.match_level == "exact"), reverse=True)
        return candidates[:top_k]

    def _score(self, segment: Segment, asset: LibraryAsset, target_aspect: str) -> Tuple[float, Dict[str, float], List[str]]:
        searchable = asset.searchable_text or " ".join(
            [
                asset.title,
                asset.description,
                " ".join(asset.tags),
                asset.category,
                asset.path,
            ]
        ).lower()
        title_tags = " ".join([asset.title, " ".join(asset.tags), asset.category]).lower()
        terms = self._segment_terms(segment)
        matched_terms = [term for term in terms if self._term_matches(term, searchable)]
        title_tag_hits = [term for term in terms if self._term_matches(term, title_tags)]

        keyword_score = min(0.34, len(matched_terms) * 0.08)
        title_tag_score = min(0.18, len(title_tag_hits) * 0.06)
        media_score = self._media_fit(segment, asset)
        aspect_score = self._aspect_fit(asset, target_aspect)
        resolution_score = self._resolution_fit(asset)
        duration_score = self._duration_fit(segment, asset)
        metadata_score = 0.06 if asset.metadata_complete else 0.02 if asset.title else 0.0

        semantic = min(1.0, keyword_score + title_tag_score + media_score)
        technical = min(1.0, aspect_score + resolution_score + duration_score)
        local_match = min(1.0, keyword_score + title_tag_score + metadata_score)
        score = min(
            1.0,
            keyword_score
            + title_tag_score
            + media_score
            + aspect_score
            + resolution_score
            + duration_score
            + metadata_score,
        )
        notes = []
        if matched_terms:
            notes.append("matched terms: {0}".format(", ".join(matched_terms[:5])))
        if title_tag_hits:
            notes.append("title/tag evidence: {0}".format(", ".join(title_tag_hits[:5])))
        if media_score > 0:
            notes.append("media type fits {0}".format(segment.scene_type))
        if aspect_score >= 0.14:
            notes.append("aspect fits target")
        elif aspect_score > 0:
            notes.append("orientation is usable")
        if resolution_score >= 0.08:
            notes.append("resolution is usable")
        if duration_score >= 0.05:
            notes.append("duration fits segment")
        if asset.warnings:
            notes.extend(asset.warnings[:2])

        breakdown = {
            "semantic": round(semantic, 3),
            "technical": round(technical, 3),
            "local_match": round(local_match, 3),
            "keyword": round(keyword_score, 3),
            "title_tags": round(title_tag_score, 3),
            "media_fit": round(media_score, 3),
            "aspect_fit": round(aspect_score, 3),
            "resolution_fit": round(resolution_score, 3),
            "duration_fit": round(duration_score, 3),
            "metadata": round(metadata_score, 3),
        }
        return score, breakdown, notes

    def _segment_terms(self, segment: Segment) -> List[str]:
        raw_terms: List[str] = []
        raw_terms.extend(segment.keywords_cn)
        raw_terms.extend(segment.keywords_en)
        raw_terms.extend(segment.search_queries)
        raw_terms.extend(segment.context_tags)
        raw_terms.append(segment.narrative_subject)
        raw_terms.append(segment.visual_brief)
        tokens: List[str] = []
        for item in raw_terms:
            value = str(item).strip().lower()
            if not value:
                continue
            tokens.append(value)
            tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_-]{2,}", value))
        return self._dedupe(tokens)

    def _term_matches(self, term: str, searchable: str) -> bool:
        if not term or len(term) < 2:
            return False
        return term in searchable

    def _media_fit(self, segment: Segment, asset: LibraryAsset) -> float:
        if segment.scene_type == "b_roll" and asset.asset_type == "video":
            return 0.16
        if segment.scene_type in {"text_card", "infographic"} and asset.asset_type == "image":
            return 0.10
        if segment.visual_type == "stock_image" and asset.asset_type == "image":
            return 0.10
        if segment.visual_type == "stock_video" and asset.asset_type == "video":
            return 0.12
        return 0.0

    def _aspect_fit(self, asset: LibraryAsset, target_aspect: str) -> float:
        if not target_aspect or not asset.orientation:
            return 0.0
        try:
            normalized = normalize_aspect(target_aspect)
        except ValueError:
            normalized = target_aspect
        if asset.aspect_ratio == normalized:
            return 0.16
        if asset.orientation == orientation_for_aspect(normalized):
            return 0.10
        return 0.0

    def _resolution_fit(self, asset: LibraryAsset) -> float:
        if not asset.width or not asset.height:
            return 0.0
        longer_edge = max(asset.width, asset.height)
        if longer_edge >= 2160:
            return 0.10
        if longer_edge >= 1080:
            return 0.08
        if longer_edge >= 720:
            return 0.04
        return 0.0

    def _duration_fit(self, segment: Segment, asset: LibraryAsset) -> float:
        if asset.asset_type != "video" or not asset.duration:
            return 0.0
        target = max(float(segment.duration_hint or 3.0), 1.0)
        if target <= asset.duration <= 30:
            return 0.07
        if asset.duration >= target:
            return 0.04
        return 0.0

    def _dedupe(self, values: List[str]) -> List[str]:
        seen = set()
        result = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _bucket(self, score: float) -> str:
        if score >= 0.75:
            return "strong"
        if score >= 0.55:
            return "ready"
        return "review"
