from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from cmm.models import MatchedSegment, MaterialCandidate, Segment


class Ranker:
    def match(self, segments: List[Segment], materials_by_segment: Dict[int, List[MaterialCandidate]]) -> List[MatchedSegment]:
        results = []
        recent_primaries: List[MaterialCandidate] = []
        for segment in segments:
            if segment.visual_type == "skip" or segment.scene_type == "talking_head":
                results.append(
                    MatchedSegment(
                        segment=segment,
                        primary=None,
                        candidates=[],
                        selection_reason="Skip segment reserved for host footage or manual editing.",
                        fallback_used=False,
                    )
                )
                continue

            candidates = sorted(
                materials_by_segment.get(segment.id, []),
                key=self._sort_key,
                reverse=True,
            )
            primary = self._choose_primary(candidates, recent_primaries, segment)
            shortlist = self._build_shortlist(candidates, limit=3, primary=primary)
            fallback_used = bool(primary and primary.match_level == "generic")
            reason = "No candidate found."
            if primary:
                reason = "Selected {0} candidate from {1}.".format(primary.match_level, primary.source_type)
                if candidates and primary.id != candidates[0].id:
                    reason += " Adjusted for visual diversity."
            results.append(
                MatchedSegment(
                    segment=segment,
                    primary=primary,
                    candidates=shortlist,
                    selection_reason=reason,
                    fallback_used=fallback_used,
                )
            )
            if primary:
                recent_primaries.append(primary)
                recent_primaries = recent_primaries[-3:]
        return results

    def _sort_key(self, item: MaterialCandidate):
        local_bonus = 0.08 if item.source_type == "local" else 0.0
        exact_bonus = 0.08 if item.match_level == "exact" else 0.03 if item.match_level == "approx" else 0.0
        resolution_bonus = 0.06 * float(item.quality_signals.get("resolution_fit", 0.0) or 0.0)
        duration_bonus = 0.04 * float(item.quality_signals.get("duration_fit", 0.0) or 0.0)
        size_bonus = 0.0
        if item.width and item.height:
            megapixels = (item.width * item.height) / 1_000_000
            size_bonus = min(0.02, megapixels / 200.0)
        duration_penalty = -0.03 if item.duration and not 3 <= item.duration <= 30 else 0.0
        return (item.relevance_score * 1.35) + local_bonus + exact_bonus + resolution_bonus + duration_bonus + size_bonus + duration_penalty

    def _choose_primary(
        self,
        candidates: List[MaterialCandidate],
        recent_primaries: List[MaterialCandidate],
        segment: Segment,
    ) -> Optional[MaterialCandidate]:
        if not candidates:
            return None
        primary = candidates[0]
        if not recent_primaries:
            return primary

        primary_score = self._sort_key(primary)
        has_video_streak = self._has_video_streak(recent_primaries)
        preferred_static = self._best_static_candidate(candidates)
        if (
            segment.scene_type == "infographic"
            and recent_primaries[-1].media_type == "video"
            and primary.media_type == "video"
            and preferred_static is not None
        ):
            relevance_gap = primary.relevance_score - preferred_static.relevance_score
            static_gap = primary_score - self._sort_key(preferred_static)
            if preferred_static.source_type == "text_card" and relevance_gap <= 0.08:
                return preferred_static
            if preferred_static.source_type == "text_card" and relevance_gap <= 0.25:
                return preferred_static
            if relevance_gap <= 0.14 or static_gap <= 0.16:
                return preferred_static

        for candidate in candidates[1:]:
            candidate_score = self._sort_key(candidate)
            score_gap = primary_score - candidate_score
            if score_gap > 0.12:
                continue

            rhythm = self._rhythm_signal(candidate, recent_primaries)
            primary_rhythm = self._rhythm_signal(primary, recent_primaries)
            source_changed = any(candidate.source_type != previous.source_type for previous in recent_primaries)
            media_changed = any(candidate.media_type != previous.media_type for previous in recent_primaries)

            if segment.scene_type == "infographic" and primary.media_type == "video" and candidate.media_type == "image" and score_gap <= 0.1:
                return candidate
            if has_video_streak and candidate.media_type == "image" and primary.media_type == "video" and score_gap <= 0.12:
                return candidate
            if rhythm > primary_rhythm and score_gap <= 0.08:
                return candidate
            if source_changed and media_changed:
                return candidate
            if source_changed and score_gap <= 0.08:
                return candidate
        return primary

    def _build_shortlist(
        self,
        candidates: List[MaterialCandidate],
        limit: int,
        primary: Optional[MaterialCandidate] = None,
    ) -> List[MaterialCandidate]:
        preferred_card = self._best_text_card(candidates)
        if len(candidates) <= limit:
            ordered = self._ordered_candidates(candidates, primary, preferred_card)
            return ordered[:limit]

        grouped = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.source_type].append(candidate)

        shortlist: List[MaterialCandidate] = []
        if primary:
            shortlist.append(primary)
        elif candidates:
            shortlist.append(candidates[0])

        if preferred_card and all(existing.id != preferred_card.id for existing in shortlist):
            shortlist.append(preferred_card)

        for provider in ("local", "pexels", "pixabay", "data_card", "text_card", "generic"):
            if len(shortlist) >= limit:
                break
            for candidate in grouped.get(provider, []):
                if self._already_present(candidate, shortlist):
                    continue
                if self._is_redundant_for_shortlist(candidate, shortlist):
                    continue
                shortlist.append(candidate)
                break

        if len(shortlist) < limit:
            for candidate in candidates:
                if self._already_present(candidate, shortlist):
                    continue
                if self._is_redundant_for_shortlist(candidate, shortlist):
                    continue
                shortlist.append(candidate)
                if len(shortlist) >= limit:
                    break

        if len(shortlist) < limit:
            for candidate in candidates:
                if self._already_present(candidate, shortlist):
                    continue
                shortlist.append(candidate)
                if len(shortlist) >= limit:
                    break

        return shortlist[:limit]

    def _rhythm_signal(self, candidate: MaterialCandidate, recent_primaries: List[MaterialCandidate]) -> float:
        signal = 0.0
        if not recent_primaries:
            return signal

        latest = recent_primaries[-1]
        if candidate.media_type != latest.media_type:
            signal += 0.08
        if candidate.source_type != latest.source_type:
            signal += 0.05

        if len(recent_primaries) >= 2:
            last_two = recent_primaries[-2:]
            if all(previous.media_type == "video" for previous in last_two) and candidate.media_type == "image":
                signal += 0.18
            if all(previous.source_type == latest.source_type for previous in last_two) and candidate.source_type != latest.source_type:
                signal += 0.08
            if all(previous.media_type == latest.media_type for previous in last_two) and candidate.media_type != latest.media_type:
                signal += 0.06
        if len(recent_primaries) >= 3:
            last_three = recent_primaries[-3:]
            if all(previous.media_type == "video" for previous in last_three) and candidate.media_type == "image":
                signal += 0.1
        return signal

    def _has_video_streak(self, recent_primaries: List[MaterialCandidate]) -> bool:
        if len(recent_primaries) < 2:
            return False
        return all(previous.media_type == "video" for previous in recent_primaries[-2:])

    def _best_static_candidate(self, candidates: List[MaterialCandidate]) -> Optional[MaterialCandidate]:
        static_candidates = [candidate for candidate in candidates if candidate.media_type == "image"]
        if not static_candidates:
            return None
        return max(static_candidates, key=self._sort_key)

    def _best_text_card(self, candidates: List[MaterialCandidate]) -> Optional[MaterialCandidate]:
        text_cards = [candidate for candidate in candidates if candidate.source_type in {"text_card", "data_card"}]
        if not text_cards:
            return None
        return max(text_cards, key=self._sort_key)

    def _ordered_candidates(
        self,
        candidates: List[MaterialCandidate],
        primary: Optional[MaterialCandidate],
        preferred_card: Optional[MaterialCandidate],
    ) -> List[MaterialCandidate]:
        ordered: List[MaterialCandidate] = []
        if primary:
            ordered.append(primary)
        if preferred_card and all(existing.id != preferred_card.id for existing in ordered):
            ordered.append(preferred_card)
        for candidate in candidates:
            if all(existing.id != candidate.id for existing in ordered):
                ordered.append(candidate)
        return ordered

    def _already_present(self, candidate: MaterialCandidate, shortlist: List[MaterialCandidate]) -> bool:
        return any(existing.id == candidate.id for existing in shortlist)

    def _is_redundant_for_shortlist(self, candidate: MaterialCandidate, shortlist: List[MaterialCandidate]) -> bool:
        if not shortlist:
            return False

        candidate_signature = self._candidate_signature(candidate)
        if any(self._candidate_signature(existing) == candidate_signature for existing in shortlist):
            return True

        same_provider_media = [
            existing
            for existing in shortlist
            if existing.source_type == candidate.source_type and existing.media_type == candidate.media_type
        ]
        if same_provider_media:
            if candidate.source_type in {"data_card", "text_card"}:
                return True
            if len(same_provider_media) >= 1 and len(shortlist) >= 2:
                return True
        return False

    def _candidate_signature(self, candidate: MaterialCandidate) -> str:
        if candidate.source_type == "data_card":
            topic = candidate.provider_meta.get("chart_topic", "general")
            kind = candidate.provider_meta.get("chart_kind", "bar")
            return "data_card:{0}:{1}".format(topic, kind)
        if candidate.source_type == "text_card":
            return "text_card"
        title = str(candidate.provider_meta.get("title", "")).strip().lower()
        if title:
            return "{0}:{1}:{2}".format(candidate.source_type, candidate.media_type, title)
        return "{0}:{1}:{2}".format(candidate.source_type, candidate.media_type, candidate.id)
