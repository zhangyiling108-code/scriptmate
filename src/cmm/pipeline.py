from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import shutil
from urllib.parse import quote_plus

from cmm.analyzer import LLMAnalyzer
from cmm.cache import FileCache
from cmm.cards import CardRenderer, ChartRenderer
from cmm.config import Settings
from cmm.fetcher import FallbackManager, StockSearchService
from cmm.fetcher.downloader import download_file
from cmm.library import LocalLibraryMatcher, scan_library
from cmm.models import AnalysisResult, MatchInput, MatchResult, MatchSummary, MaterialCandidate, SearchResult, SegmentMatch
from cmm.outputs import write_match_outputs
from cmm.ranker import Ranker
from cmm.scorer import SemanticScorer


async def analyze_script(text: str, settings: Settings, cache: FileCache, aspect: str = "9:16") -> AnalysisResult:
    cache_key = _analysis_cache_key(text=text, aspect=aspect, settings=settings)
    cached = cache.load_json("analysis", cache_key)
    if cached is not None:
        return AnalysisResult(**cached)
    analyzer = LLMAnalyzer(settings.planner_model, allow_fallback=settings.downgrade.planner_fallback)
    result = await analyzer.analyze(text, aspect)
    cache.save_json("analysis", cache_key, result.model_dump())
    return result


async def search_single_query(
    query: str,
    settings: Settings,
    cache: FileCache,
    data_dir: str,
    source: str = "all",
    top_k: int = 5,
    aspect: str = "9:16",
    resolution: str = "1080",
) -> SearchResult:
    effective_matching = _matching_for_run(settings.matching, aspect, resolution)
    fallback_manager = FallbackManager(
        mapping_path=str(Path(data_dir) / "keyword_mapping.json"),
        generic_dir=str(Path(data_dir) / "generic_footage"),
    )
    service = StockSearchService(settings.sources, effective_matching, fallback_manager, cache)
    return await service.search_query(query, source=source, top_k=top_k)


async def match_script(
    match_input: MatchInput,
    settings: Settings,
    data_dir: str,
    library_root: Optional[str] = None,
    library_meta: Optional[str] = None,
) -> MatchResult:
    requested_results = max(match_input.top_results, 3)
    output_dir = Path(match_input.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = settings.output.cache_dir or str(output_dir / "cache")
    cache = FileCache(cache_dir)
    effective_matching = _matching_for_run(settings.matching, match_input.aspect, match_input.resolution)

    analysis = await analyze_script(match_input.text, settings, cache, aspect=match_input.aspect)
    analysis_fallback_used = analysis.overall_style.startswith("heuristic fallback")
    if match_input.analysis_only:
        result = MatchResult(
            script_file="",
            created_at=_now_iso(),
            total_segments=len(analysis.segments),
            analysis=analysis,
            segments=[SegmentMatch(segment=segment, action="analyzed") for segment in analysis.segments],
            match_summary=MatchSummary(skipped=sum(1 for segment in analysis.segments if segment.visual_type == "skip")),
            output_dir=str(output_dir),
            warnings=["Planner fallback used local heuristic analysis."] if analysis_fallback_used else [],
            cache_hits={"analysis": 1 if cache.has("analysis", _analysis_cache_key(match_input.text, match_input.aspect, settings)) else 0},
        )
        write_match_outputs(result, str(output_dir))
        return result

    assets = []
    if library_root:
        assets = scan_library(library_root, metadata_path=library_meta or "").assets

    local_matcher = LocalLibraryMatcher()
    fallback_manager = FallbackManager(
        mapping_path=str(Path(data_dir) / "keyword_mapping.json"),
        generic_dir=str(Path(data_dir) / "generic_footage"),
    )
    stock_search = StockSearchService(settings.sources, effective_matching, fallback_manager, cache)
    scorer = SemanticScorer(settings.judge_model, cache, allow_fallback=settings.downgrade.judge_fallback)
    card_renderer = CardRenderer(str(Path(data_dir) / "card_templates"), settings.cards)
    chart_renderer = ChartRenderer(settings.cards, settings.generation)
    ranker = Ranker()

    materials_by_segment: Dict[int, List[MaterialCandidate]] = {}
    downloads: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []
    segment_notes: Dict[int, List[str]] = {}
    segment_fallbacks: Dict[int, bool] = {}
    if analysis_fallback_used:
        warnings.append("Planner fallback used local heuristic analysis.")

    for segment in analysis.segments:
        segment_notes[segment.id] = []
        segment_fallbacks[segment.id] = False
        if segment.visual_type == "skip":
            materials_by_segment[segment.id] = []
            continue

        segment_candidates: List[MaterialCandidate] = []
        local_candidates = local_matcher.match(segment, assets, top_k=max(match_input.top_results, settings.matching.top_results))
        if local_candidates:
            segment_candidates.extend(local_candidates)

        if segment.visual_type in {"stock_video", "stock_image"}:
            raw_candidates = await stock_search.search(segment)
            scored_candidates = await scorer.score_candidates(segment, raw_candidates)
            strong_candidates = [item for item in scored_candidates if item.relevance_score >= settings.matching.min_score]
            if segment.scene_type == "infographic":
                infographic_threshold = max(effective_matching.strong_score, 0.82)
                strong_candidates = [item for item in strong_candidates if item.relevance_score >= infographic_threshold]
            if strong_candidates:
                segment_candidates.extend(strong_candidates)
            supplemental_candidates = [item for item in scored_candidates if item.id not in {candidate.id for candidate in segment_candidates}]
            if len(segment_candidates) < requested_results and supplemental_candidates:
                segment_candidates.extend(supplemental_candidates[: requested_results - len(segment_candidates)])
            if len(segment_candidates) < requested_results:
                real_supplemental = await _supplement_real_candidates(
                    segment=segment,
                    existing=segment_candidates,
                    requested_results=requested_results,
                    stock_search=stock_search,
                    scorer=scorer,
                )
                for candidate in real_supplemental:
                    if candidate.id in {existing.id for existing in segment_candidates}:
                        continue
                    segment_candidates.append(candidate)
                    if len(segment_candidates) >= requested_results:
                        break
            if len(segment_candidates) < requested_results and settings.downgrade.search_fallback:
                fallback_candidates = await _fallback_candidates(segment, stock_search, scorer)
                for candidate in fallback_candidates:
                    if candidate.id in {existing.id for existing in segment_candidates}:
                        continue
                    segment_candidates.append(candidate)
                    segment_fallbacks[segment.id] = True
                    if len(segment_candidates) >= requested_results:
                        break
            elif len(segment_candidates) < requested_results:
                segment_notes[segment.id].append(
                    "已优先用上下文扩展和真实素材补搜，但仍不足 {0} 条；默认不降级，是否继续降级需人工确认。".format(
                        requested_results
                    )
                )
            if (
                settings.downgrade.generated_fallback
                and segment.scene_type == "infographic"
                and not any(_is_candidate_acceptable(segment, candidate, effective_matching, settings) for candidate in segment_candidates)
            ):
                segment_candidates.append(await _generated_fallback(segment, chart_renderer, card_renderer, output_dir))
                segment_fallbacks[segment.id] = True
            elif (
                segment.scene_type == "infographic"
                and not settings.downgrade.generated_fallback
                and not any(_is_candidate_acceptable(segment, candidate, effective_matching, settings) for candidate in segment_candidates)
            ):
                segment_notes[segment.id].append("未自动生成解释卡或图表；如需降级到生成型素材，请显式允许 generated fallback。")
        elif segment.visual_type == "data_card":
            if settings.downgrade.generated_fallback:
                segment_candidates.append(await chart_renderer.render(segment, str(output_dir / "segments" / _segment_dir(segment.id))))
                segment_fallbacks[segment.id] = True
            else:
                search_segment = segment.model_copy(update={"visual_type": "stock_image", "scene_type": "infographic"})
                raw_candidates = await stock_search.search(search_segment)
                scored_candidates = await scorer.score_candidates(search_segment, raw_candidates)
                segment_candidates.extend(scored_candidates[:requested_results])
                segment_notes[segment.id].append("该段原本更适合解释卡，但当前默认不降级；已改为返回真实素材候选供人工选择。")
        elif segment.visual_type == "text_card":
            if settings.downgrade.generated_fallback:
                segment_candidates.append(await card_renderer.render(segment, str(output_dir / "segments" / _segment_dir(segment.id))))
                segment_fallbacks[segment.id] = True
            else:
                search_segment = segment.model_copy(update={"visual_type": "stock_image", "scene_type": "b_roll"})
                raw_candidates = await stock_search.search(search_segment)
                scored_candidates = await scorer.score_candidates(search_segment, raw_candidates)
                segment_candidates.extend(scored_candidates[:requested_results])
                segment_notes[segment.id].append("该段原本更适合文字总结卡，但当前默认不降级；已改为返回真实素材候选供人工选择。")

        materials_by_segment[segment.id] = segment_candidates

    matched = ranker.match(analysis.segments, materials_by_segment)
    segment_results: List[SegmentMatch] = []
    for item in matched:
        acceptable_primary = item.primary if _is_candidate_acceptable(item.segment, item.primary, effective_matching, settings) else None
        if acceptable_primary is None and item.primary is not None:
            segment_notes[item.segment.id].append("已找到候选，但主选未达到当前质量门槛；保留链接供人工选择，默认不自动降级。")
        chosen = acceptable_primary
        alternatives = (
            item.candidates[1: requested_results]
            if chosen is not None and item.candidates
            else item.candidates[:requested_results]
        )
        if match_input.save_candidates:
            dest_dir = output_dir / "segments" / _segment_dir(item.segment.id)
            dest_dir.mkdir(parents=True, exist_ok=True)
            if chosen:
                try:
                    file_path = await _store_candidate(chosen, dest_dir / ("recommended" + _candidate_suffix(chosen)))
                    chosen.provider_meta["downloaded_path"] = file_path
                    downloads.append(file_path)
                except Exception as exc:
                    warnings.append("Download failed for segment {0}: {1}".format(item.segment.id, exc))
            if alternatives:
                alternatives_dir = dest_dir / "alternatives"
                alternatives_dir.mkdir(parents=True, exist_ok=True)
                for index, alternative in enumerate(alternatives, start=1):
                    try:
                        file_path = await _store_candidate(
                            alternative,
                            alternatives_dir / ("alt_{0:02d}".format(index) + _candidate_suffix(alternative)),
                        )
                        alternative.provider_meta["downloaded_path"] = file_path
                        downloads.append(file_path)
                    except Exception as exc:
                        warnings.append(
                            "Alternative download failed for segment {0}, option {1}: {2}".format(item.segment.id, index, exc)
                        )

        segment_results.append(
            SegmentMatch(
                segment=item.segment,
                chosen=chosen,
                alternatives=alternatives,
                external_search_links=_external_search_links(item.segment, settings),
                fallback_used=segment_fallbacks.get(item.segment.id, False),
                action=_action_for_segment(item.segment, chosen),
                notes=[
                    note
                    for note in [
                        _strategy_note(item.segment, chosen),
                        item.selection_reason if chosen is not None else "",
                        *segment_notes.get(item.segment.id, []),
                    ]
                    if note
                ],
            )
        )

    result = MatchResult(
        script_file="",
        created_at=_now_iso(),
        total_segments=len(analysis.segments),
        analysis=analysis,
        segments=segment_results,
        match_summary=_build_summary(segment_results),
        output_dir=str(output_dir),
        downloads=downloads,
        errors=errors,
        warnings=warnings,
        cache_hits={},
    )
    write_match_outputs(result, str(output_dir))
    return result


async def _fallback_candidates(segment, stock_search, scorer) -> List[MaterialCandidate]:
    mapped_queries = stock_search.mapped_queries(segment)
    if mapped_queries:
        mapped_segment = segment.model_copy(update={"search_queries": mapped_queries})
        raw_candidates = await stock_search.search(mapped_segment)
        scored_candidates = await scorer.score_candidates(segment, raw_candidates)
        filtered = [item for item in scored_candidates if item.relevance_score >= 0.55]
        if filtered:
            for item in filtered:
                item.provider_meta["fallback_stage"] = "mapping"
            return filtered
    return stock_search.generic_candidates(segment, top_k=3)


async def _supplement_real_candidates(segment, existing, requested_results, stock_search, scorer) -> List[MaterialCandidate]:
    if len(existing) >= requested_results:
        return []

    expansions = []
    layers = segment.search_query_layers or {}
    for key in ("context", "l3", "l4"):
        queries = layers.get(key, [])
        if queries:
            expansions.append(segment.model_copy(update={"search_queries": queries}))

    alternate_visual_type = "stock_image" if segment.visual_type == "stock_video" else "stock_video"
    alternate_scene_type = "infographic" if alternate_visual_type == "stock_image" else "b_roll"
    alternate_queries = (
        layers.get("context", [])
        + layers.get("l2", [])
        + layers.get("l3", [])
    )
    if alternate_queries:
        expansions.append(
            segment.model_copy(
                update={
                    "visual_type": alternate_visual_type,
                    "scene_type": alternate_scene_type,
                    "search_queries": alternate_queries,
                }
            )
        )

    supplemental: List[MaterialCandidate] = []
    seen = {candidate.id for candidate in existing}
    for expanded_segment in expansions:
        raw_candidates = await stock_search.search(expanded_segment)
        scored_candidates = await scorer.score_candidates(expanded_segment, raw_candidates)
        for candidate in scored_candidates:
            if candidate.id in seen:
                continue
            seen.add(candidate.id)
            supplemental.append(candidate)
            if len(existing) + len(supplemental) >= requested_results:
                return supplemental
    return supplemental


async def _generated_fallback(segment, chart_renderer, card_renderer, output_dir: Path):
    segment_dir = output_dir / "segments" / _segment_dir(segment.id)
    if segment.visual_type == "stock_image" or segment.scene_type == "infographic":
        return await chart_renderer.render(segment, str(segment_dir))
    return await card_renderer.render(segment, str(segment_dir))


def _is_candidate_acceptable(segment, candidate: Optional[MaterialCandidate], matching, settings: Settings) -> bool:
    if candidate is None:
        return False
    if candidate.source_type in {"data_card", "text_card"}:
        return settings.downgrade.generated_fallback
    threshold = matching.min_score
    if segment.scene_type == "infographic":
        threshold = max(matching.strong_score, 0.82)
    return candidate.relevance_score >= threshold


def _matching_for_run(matching, aspect: str, resolution: str):
    payload = matching.model_dump()
    payload["video_orientation"] = _orientation_for_aspect(aspect)
    payload["video_min_resolution"] = _min_resolution_for_request(resolution, matching.video_min_resolution)
    return type(matching)(**payload)


def _orientation_for_aspect(aspect: str) -> str:
    normalized = (aspect or "").replace("*", ":").strip()
    if normalized == "16:9":
        return "horizontal"
    if normalized == "1:1":
        return "square"
    return "vertical"


def _min_resolution_for_request(resolution: str, default: int) -> int:
    normalized = str(resolution or "").strip().lower()
    if normalized in {"4k", "2160"}:
        return 2160
    if normalized in {"720", "hd"}:
        return 720
    if normalized in {"1080", "fullhd", "fhd"}:
        return 1080
    return default


def _analysis_cache_key(text: str, aspect: str, settings: Settings) -> str:
    return "{0}|{1}|{2}|{3}".format(text, aspect, settings.cards.theme, settings.planner_model.model)


def _build_summary(segments: List[SegmentMatch]) -> MatchSummary:
    summary = MatchSummary()
    for item in segments:
        if item.segment.visual_type == "skip":
            summary.skipped += 1
            continue
        if item.chosen is None:
            continue
        if item.chosen.source_type in {"data_card", "text_card"}:
            summary.generated += 1
        elif item.chosen.match_level == "exact":
            summary.exact += 1
        elif item.chosen.match_level == "approx":
            summary.approximate += 1
        else:
            summary.generic_real += 1
    return summary


def _action_for_segment(segment, chosen: Optional[MaterialCandidate]) -> str:
    if segment.visual_type == "skip":
        return "skip"
    if chosen is None:
        return "unmatched"
    if chosen.source_type in {"data_card", "text_card"}:
        return "generated"
    if chosen.provider_meta.get("downloaded_path"):
        return "downloaded"
    if chosen.uri.startswith("http"):
        return "selected_link"
    return "selected"


def _strategy_note(segment, chosen: Optional[MaterialCandidate]) -> str:
    if segment.visual_type == "skip":
        return "策略：该段保留给口播开场或人工镜头，不自动匹配素材。"
    if segment.visual_type == "text_card":
        return "策略：该段属于总结/强调，优先生成文字卡以保证信息清晰。"
    if segment.visual_type == "data_card":
        if chosen and chosen.source_type == "data_card":
            topic = chosen.provider_meta.get("chart_topic")
            kind = chosen.provider_meta.get("chart_kind")
            if topic or kind:
                return "策略：该段属于抽象解释，优先生成 {0}{1} 解释卡。".format(
                    topic or "general",
                    "/{0}".format(kind) if kind else "",
                )
        return "策略：该段属于抽象解释，优先生成图表或解释卡。"
    if segment.visual_type == "stock_image":
        return "策略：该段偏解释型，优先静态高信息密度素材而不是连续视频。"
    return "策略：该段有明确可拍场景，优先匹配真实实景视频素材。"


def _segment_dir(segment_id: int) -> str:
    return "{0:03d}".format(segment_id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _store_candidate(candidate: MaterialCandidate, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if candidate.uri.startswith("http://") or candidate.uri.startswith("https://"):
        temp_path = await download_file(candidate.uri, str(destination.parent))
        temp = Path(temp_path)
        if temp != destination:
            shutil.move(str(temp), str(destination))
        return str(destination)
    source = Path(candidate.uri)
    if source.exists():
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        return str(destination)
    destination.write_text(candidate.uri, encoding="utf-8")
    return str(destination)


def _candidate_suffix(candidate: MaterialCandidate) -> str:
    source = Path(candidate.uri)
    suffix = source.suffix.lower()
    if suffix:
        return suffix
    return ".mp4" if candidate.media_type == "video" else ".png"


def _external_search_links(segment, settings: Settings) -> List[Dict[str, str]]:
    links = []
    query = _segment_search_query(segment)
    if not query:
        return links
    encoded = quote_plus(query)
    for source in settings.sources.configured_external_sources():
        template = (source.search_url_template or "").strip()
        if not template:
            continue
        links.append(
            {
                "name": source.name,
                "license": source.license,
                "kind": source.kind,
                "priority": str(source.priority),
                "query": query,
                "url": template.replace("{query}", encoded),
                "home_url": source.home_url,
                "notes": source.notes,
            }
        )
    return links


def _segment_search_query(segment) -> str:
    layers = segment.search_query_layers or {}
    for key in ("context", "l1", "l2", "l3", "l4"):
        queries = layers.get(key, [])
        if queries:
            return queries[0]
    if segment.search_queries:
        return segment.search_queries[0]
    if segment.visual_brief:
        return segment.visual_brief
    return segment.text
