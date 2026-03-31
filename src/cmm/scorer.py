from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Tuple

from cmm.cache import FileCache
from cmm.config import ModelSettings
from cmm.models import MaterialCandidate, Segment
from cmm.utils.http import build_async_client


class SemanticScorer:
    def __init__(self, settings: ModelSettings, cache: FileCache, allow_fallback: bool = False):
        self.settings = settings
        self.cache = cache
        self.allow_fallback = allow_fallback

    async def score_candidates(self, segment: Segment, candidates: List[MaterialCandidate], batch_size: int = 4) -> List[MaterialCandidate]:
        if not candidates:
            return []
        if not self.settings.base_url or not self.settings.api_key:
            raise ValueError("Judge model requires base_url and api_key.")

        scored: List[MaterialCandidate] = []
        for offset in range(0, len(candidates), batch_size):
            batch = candidates[offset : offset + batch_size]
            cache_key = self._cache_key(segment, batch)
            cached = self.cache.load_json("judge", cache_key)
            if cached is None:
                try:
                    payload = await self._request_scores(segment, batch)
                except Exception:
                    if not self.allow_fallback:
                        raise
                    payload = self._heuristic_fallback_scores(segment, batch)
                self.cache.save_json("judge", cache_key, payload)
            else:
                payload = cached
            score_map = {}
            number_map = {}
            ordered_items = []
            for position, item in enumerate(payload, start=1):
                score_map[str(item.get("id", ""))] = item
                number_map[str(item.get("candidate_number", ""))] = item
                ordered_items.append(item)
            for position, candidate in enumerate(batch, start=1):
                item = (
                    score_map.get(candidate.id)
                    or score_map.get(str(position))
                    or number_map.get(str(position))
                    or (ordered_items[position - 1] if position - 1 < len(ordered_items) else None)
                )
                if not item:
                    continue
                candidate.relevance_score = float(item.get("score", 0.0))
                adjustment_note = self._apply_editorial_adjustments(segment, candidate)
                candidate.match_level = self._level_from_score(candidate.relevance_score)
                base_reason = str(item.get("reason", ""))
                candidate.reason = "{0} {1}".format(base_reason, adjustment_note).strip() if adjustment_note else base_reason
                scored.append(candidate)
        return scored

    def _heuristic_fallback_scores(self, segment: Segment, candidates: List[MaterialCandidate]) -> List[Dict[str, object]]:
        fallback_scores = []
        target_terms = self._collect_segment_terms(segment)
        for position, candidate in enumerate(candidates, start=1):
            score, reason = self._heuristic_candidate_score(segment, candidate, target_terms)
            fallback_scores.append(
                {
                    "id": candidate.id,
                    "candidate_number": position,
                    "score": round(score, 2),
                    "reason": reason,
                }
            )
        return fallback_scores

    def _heuristic_candidate_score(
        self,
        segment: Segment,
        candidate: MaterialCandidate,
        target_terms: List[str],
    ) -> Tuple[float, str]:
        score = 0.52
        evidence = self._collect_candidate_terms(candidate)
        overlap = [term for term in target_terms if term in evidence]
        overlap_ratio = (len(overlap) / len(target_terms)) if target_terms else 0.0
        score += min(0.22, overlap_ratio * 0.35)

        if segment.visual_type == "stock_image":
            score += 0.08 if candidate.media_type == "image" else -0.04
        elif segment.visual_type == "stock_video":
            score += 0.08 if candidate.media_type == "video" else -0.04

        if segment.scene_type == "infographic":
            if candidate.media_type == "image":
                score += 0.05
            if any(token in evidence for token in ("diagram", "illustration", "anatomy", "cells", "microscope")):
                score += 0.06

        if candidate.width and candidate.height:
            longer_edge = max(candidate.width, candidate.height)
            shorter_edge = min(candidate.width, candidate.height)
            if longer_edge >= 1920:
                score += 0.04
            elif longer_edge < 1080:
                score -= 0.06
            if candidate.media_type == "video" and candidate.height > candidate.width:
                score += 0.03
            if candidate.media_type == "image" and shorter_edge >= 1080:
                score += 0.03

        if candidate.duration:
            if 4 <= candidate.duration <= 18:
                score += 0.03
            elif candidate.duration > 35:
                score -= 0.04

        score = max(0.45, min(0.88, score))
        if overlap:
            reason = "Judge unavailable; heuristic score from term overlap ({0}) and basic quality checks.".format(
                ", ".join(overlap[:3])
            )
        else:
            reason = "Judge unavailable; heuristic score from media fit and basic quality checks."
        return score, reason

    def _collect_segment_terms(self, segment: Segment) -> List[str]:
        raw_terms = []
        raw_terms.extend(segment.keywords_en)
        raw_terms.extend(segment.search_queries)
        raw_terms.extend(segment.visual_brief.split())
        tokens: List[str] = []
        for item in raw_terms:
            tokens.extend(self._tokenize_english(item))
        return self._dedupe_terms(tokens)

    def _collect_candidate_terms(self, candidate: MaterialCandidate) -> set[str]:
        fields = []
        fields.extend(candidate.tags)
        fields.append(candidate.provider_meta.get("title", ""))
        fields.append(candidate.source_page)
        fields.append(candidate.reason)
        tokens: List[str] = []
        for item in fields:
            tokens.extend(self._tokenize_english(str(item)))
        return set(tokens)

    def _tokenize_english(self, value: str) -> List[str]:
        return [token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value.lower()) if token not in {"video", "photo", "footage"}]

    def _dedupe_terms(self, items: List[str]) -> List[str]:
        seen = set()
        result = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    def _apply_editorial_adjustments(self, segment: Segment, candidate: MaterialCandidate) -> str:
        evidence = self._collect_candidate_terms(candidate)
        segment_terms = set(self._collect_segment_terms(segment))
        geo_note = self._apply_geo_adjustments(segment, candidate, evidence, segment_terms)
        if segment.scene_type != "infographic":
            return geo_note

        explanatory_terms = {
            "metabolism",
            "metabolic",
            "health",
            "body",
            "process",
            "mechanism",
            "human",
            "diagram",
            "illustration",
            "anatomy",
            "cells",
            "science",
            "medical",
        }
        ingredient_terms = {
            "beetroot",
            "tea",
            "herbs",
            "herbal",
            "leaves",
            "vegetables",
            "vegetable",
            "food",
            "ingredient",
            "ingredients",
            "spices",
            "fresh",
            "drying",
        }

        explanatory_overlap = explanatory_terms & (segment_terms | evidence)
        ingredient_overlap = ingredient_terms & evidence
        body_context_terms = {"body", "human", "diagram", "illustration", "anatomy", "cells", "medical", "science"}
        has_body_context = bool(body_context_terms & evidence)

        if explanatory_overlap and ingredient_overlap and not has_body_context:
            candidate.relevance_score = max(0.45, round(candidate.relevance_score - 0.22, 2))
            note = "Penalized because it is an isolated ingredient/plant visual without enough explanatory body or mechanism context."
            return "{0} {1}".format(geo_note, note).strip()

        if "metabolism" in segment_terms and "metabolism" not in evidence and ingredient_overlap and not has_body_context:
            candidate.relevance_score = max(0.45, round(candidate.relevance_score - 0.16, 2))
            note = "Penalized because it suggests plants or food, but does not visually explain metabolism."
            return "{0} {1}".format(geo_note, note).strip()

        return geo_note

    def _apply_geo_adjustments(
        self,
        segment: Segment,
        candidate: MaterialCandidate,
        evidence: set[str],
        segment_terms: set[str],
    ) -> str:
        geo_policy = self._segment_geo_policy(segment, segment_terms)
        if not geo_policy:
            return ""
        primary_countries = geo_policy["primary"]
        allowed_countries = geo_policy["allowed"]
        candidate_countries = self._detect_geo_entities(evidence)
        notes = []
        if candidate_countries and not (candidate_countries & allowed_countries):
            candidate.relevance_score = max(0.40, round(candidate.relevance_score - 0.24, 2))
            notes.append(
                "Penalized because the asset suggests a geography outside the segment context ({0}); expected {1}.".format(
                    ", ".join(sorted(candidate_countries)[:3]),
                    ", ".join(sorted(primary_countries)[:3]),
                )
            )
        elif candidate_countries & primary_countries:
            candidate.relevance_score = min(0.95, round(candidate.relevance_score + 0.08, 2))
            notes.append(
                "Boosted because the asset carries primary geography signals ({0}).".format(
                    ", ".join(sorted(candidate_countries & primary_countries)[:3])
                )
            )
        elif candidate_countries & allowed_countries:
            candidate.relevance_score = min(0.92, round(candidate.relevance_score + 0.03, 2))
            notes.append(
                "Allowed because the asset matches an explicitly referenced comparison geography ({0}).".format(
                    ", ".join(sorted(candidate_countries & allowed_countries)[:3])
                )
            )
        return " ".join(notes).strip()

    def _segment_geo_policy(self, segment: Segment, segment_terms: set[str]) -> Dict[str, set[str]]:
        context_blob = " ".join(
            [
                segment.text,
                segment.narrative_subject,
                segment.context_statement,
                " ".join(segment.context_tags),
                " ".join(segment.keywords_en),
                " ".join(segment.search_queries),
            ]
        ).lower()
        segment_blob = " ".join(
            [
                segment.text,
                segment.context_statement,
                " ".join(segment.keywords_en),
                " ".join(segment.search_queries),
            ]
        ).lower()
        primary = self._detect_geo_entities(self._tokenize_english(segment.narrative_subject.lower()))
        if not primary:
            primary = self._first_detected_geo(
                [
                    segment.narrative_subject,
                    segment.context_statement,
                    " ".join(segment.context_tags),
                    segment.text,
                ]
            )
        if not primary:
            primary = self._detect_geo_entities(self._tokenize_english(context_blob))
        if not primary:
            return {}
        allowed = set(primary)
        if self._allows_geo_comparison(segment_blob):
            allowed |= self._detect_geo_entities(self._tokenize_english(segment_blob))
        return {"primary": primary, "allowed": allowed}

    def _allows_geo_comparison(self, text: str) -> bool:
        hints = (
            "compare",
            "comparison",
            "versus",
            "vs",
            "against",
            "competition",
            "rival",
            "rivalry",
            "对比",
            "比较",
            "相比",
            "竞赛",
            "竞争",
            "角力",
            "博弈",
            "三足鼎立",
        )
        return any(hint in text for hint in hints)

    def _detect_geo_entities(self, evidence: Iterable[str]) -> set[str]:
        tokens = set(evidence)
        detected = set()
        geo_map = {
            "china": {
                "china",
                "chinese",
                "shanghai",
                "shenzhen",
                "beijing",
                "guangzhou",
                "chongqing",
                "pudong",
                "huangpu",
                "hangzhou",
                "zhuhai",
                "macau",
            },
            "united states": {
                "america",
                "american",
                "united",
                "states",
                "usa",
                "u.s",
                "washington",
                "new",
                "york",
                "nyc",
                "silicon",
                "valley",
            },
            "japan": {"japan", "japanese", "tokyo", "osaka", "fuji"},
            "south korea": {"korea", "korean", "seoul", "busan"},
            "hong kong": {"hong", "kong"},
            "europe": {"europe", "european", "eu", "germany", "france", "italy", "switzerland", "scotland"},
            "thailand": {"thailand", "bangkok"},
        }
        for label, hints in geo_map.items():
            if tokens & hints:
                detected.add(label)
        return detected

    def _first_detected_geo(self, evidence_blobs: List[str]) -> set[str]:
        for blob in evidence_blobs:
            detected = self._detect_geo_entities(self._tokenize_english(blob.lower()))
            if detected:
                return detected
        return set()

    async def _request_scores(self, segment: Segment, candidates: List[MaterialCandidate]) -> List[Dict[str, object]]:
        headers = {"Authorization": "Bearer {0}".format(self.settings.api_key)}
        content = [
            {
                "type": "text",
                "text": (
                    "You are a visual material matching expert for documentary-style short videos. Score each candidate from 0 to 1 for how well it matches this Chinese script segment. "
                    "Return strict JSON only. Use the exact candidate id that was provided. "
                    "Be conservative. A high score means the material is not only related, but also editorially useful and visually specific. "
                    "Score rubric: 0.85-1.0 = directly expresses the segment with strong visual clarity; 0.60-0.84 = partially related but missing an important concept; below 0.60 = generic, decorative, weakly related, or misleading. "
                    "Penalize generic stock, isolated ingredient or object close-ups, and pretty visuals that require too much viewer inference. "
                    "For health, metabolism, mechanism, or cause-effect segments, prefer visuals that communicate relationship, body context, science context, or explanatory clarity over a single food or plant close-up. "
                    "Respect geography and narrative subject. The primary country or region should match the segment context, but if the segment explicitly compares or contrasts with another country or rival, that comparison geography is allowed and should not be penalized. "
                    "Preferred output format: {{\"scores\": [{{\"candidate_number\": 1, \"id\": \"...\", \"score\": 0.82, \"reason\": \"...\"}}]}}. "
                    "Segment scene_type: {0}; visual_type: {1}; text: {2}; narrative_subject: {3}; context: {4}".format(
                        segment.scene_type,
                        segment.visual_type,
                        segment.text,
                        segment.narrative_subject,
                        segment.context_statement,
                    )
                ),
            }
        ]
        for index, candidate in enumerate(candidates, start=1):
            content.append(
                {
                    "type": "text",
                    "text": "Candidate {0}: id={1}, provider={2}, media_type={3}, source_page={4}".format(
                        index,
                        candidate.id,
                        candidate.source_type,
                        candidate.media_type,
                        candidate.source_page,
                    ),
                }
            )
            if candidate.thumbnail_url or candidate.preview_uri:
                content.append({"type": "image_url", "image_url": {"url": candidate.thumbnail_url or candidate.preview_uri}})
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        async with build_async_client(timeout=max(float(self.settings.timeout_seconds), 5.0)) as client:
            response = await client.post(
                "{0}/chat/completions".format(self.settings.base_url.rstrip("/")),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(self._extract_json(raw))
        items = parsed.get("scores", parsed if isinstance(parsed, list) else [])
        normalized = []
        for position, candidate in enumerate(candidates, start=1):
            item = next(
                (
                    entry
                    for entry in items
                    if str(entry.get("id")) == candidate.id
                    or str(entry.get("id")) == str(position)
                    or str(entry.get("candidate_number")) == str(position)
                ),
                None,
            )
            if item is None:
                item = {
                    "id": candidate.id,
                    "candidate_number": position,
                    "score": 0.4,
                    "reason": "Model returned no score for this candidate.",
                }
            normalized.append(item)
        return normalized

    def _cache_key(self, segment: Segment, batch: List[MaterialCandidate]) -> str:
        return json.dumps(
            {
                "segment": segment.text,
                "model": self.settings.model,
                "provider": self.settings.provider,
                "candidates": [
                    {
                        "id": candidate.id,
                        "thumb": candidate.thumbnail_url or candidate.preview_uri,
                        "query": candidate.provider_meta.get("query", ""),
                    }
                    for candidate in batch
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _extract_json(self, raw: str) -> str:
        start = raw.find("{")
        if start == -1:
            start = raw.find("[")
        if start == -1:
            raise ValueError("Judge model response does not contain JSON.")
        open_char = raw[start]
        close_char = "}" if open_char == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(raw)):
            char = raw[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    return raw[start : index + 1]
        raise ValueError("Judge model response does not contain a complete JSON block.")

    def _level_from_score(self, score: float) -> str:
        if score >= 0.85:
            return "exact"
        if score >= 0.70:
            return "approx"
        return "generic"
