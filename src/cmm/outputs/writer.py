from __future__ import annotations

import csv
from pathlib import Path

from cmm.models import MatchResult, model_dump_compat
from cmm.outputs.labels import (
    asset_class,
    confidence_band,
    crop_risk,
    duration_fit,
    orientation_label,
    quality_tier,
    resolution_label,
    review_priority,
    review_rank,
    rhythm_tag,
    selection_tag,
    source_label,
    use_status,
)
from cmm.outputs.report import build_report
from cmm.utils.files import ensure_dir, write_json


def write_match_outputs(result: MatchResult, output_dir: str) -> None:
    target = ensure_dir(output_dir)
    write_json(str(Path(target) / "analysis.json"), model_dump_compat(result.analysis))
    write_json(str(Path(target) / "manifest.json"), _build_manifest(result))
    Path(target, "summary.md").write_text(build_report(result), encoding="utf-8")
    _write_segments_overview_csv(result, Path(target) / "segments_overview.csv")

    segments_dir = ensure_dir(str(Path(target) / "segments"))
    for item in result.segments:
        segment_dir = ensure_dir(str(Path(segments_dir) / "{0:03d}".format(item.segment.id)))
        write_json(str(Path(segment_dir) / "segment.json"), model_dump_compat(item))


def _write_segments_overview_csv(result: MatchResult, path: Path) -> None:
    fieldnames = [
        "id",
        "segment_role",
        "text",
        "narrative_subject",
        "context_statement",
        "context_tags",
        "visual_type",
        "scene_type",
        "asset_class",
        "rhythm_tag",
        "use_status",
        "confidence_band",
        "review_priority",
        "review_rank",
        "recommended_duration",
        "duration_fit",
        "resolution",
        "orientation",
        "quality_tier",
        "crop_risk",
        "source_label",
        "direct_url",
        "source_page",
        "external_search_links",
        "selection_tag",
        "score",
        "fallback_used",
        "strategy",
        "edit_suggestion",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for item in result.segments:
            chosen = item.chosen
            writer.writerow(
                {
                    "id": item.segment.id,
                    "segment_role": item.segment.segment_role,
                    "text": item.segment.text,
                    "narrative_subject": item.segment.narrative_subject,
                    "context_statement": item.segment.context_statement,
                    "context_tags": "|".join(item.segment.context_tags),
                    "visual_type": item.segment.visual_type,
                    "scene_type": item.segment.scene_type,
                    "asset_class": asset_class(item),
                    "rhythm_tag": rhythm_tag(item),
                    "use_status": use_status(item),
                    "confidence_band": confidence_band(item),
                    "review_priority": review_priority(item),
                    "review_rank": review_rank(item),
                    "recommended_duration": item.segment.duration_hint,
                    "duration_fit": duration_fit(chosen),
                    "resolution": resolution_label(chosen),
                    "orientation": orientation_label(chosen),
                    "quality_tier": quality_tier(chosen),
                    "crop_risk": crop_risk(chosen),
                    "source_label": source_label(chosen) if chosen else "",
                    "direct_url": chosen.uri if chosen else "",
                    "source_page": chosen.source_page if chosen else "",
                    "external_search_links": " | ".join(link["url"] for link in item.external_search_links),
                    "selection_tag": selection_tag(chosen, role="chosen") if chosen else "",
                    "score": chosen.relevance_score if chosen else "",
                    "fallback_used": item.fallback_used,
                    "strategy": item.notes[0] if item.notes else "",
                    "edit_suggestion": _edit_suggestion(item),
                }
            )


def _build_manifest(result: MatchResult):
    return {
        "script_file": result.script_file,
        "created_at": result.created_at,
        "total_segments": result.total_segments,
        "match_summary": model_dump_compat(result.match_summary),
        "segments": [
            {
                "id": item.segment.id,
                "text": item.segment.text,
                "segment_role": item.segment.segment_role,
                "narrative_subject": item.segment.narrative_subject,
                "context_statement": item.segment.context_statement,
                "context_tags": item.segment.context_tags,
                "type": item.segment.visual_type,
                "scene_type": item.segment.scene_type,
                "visual_brief": item.segment.visual_brief,
                "recommended_duration": item.segment.duration_hint,
                "asset_class": asset_class(item),
                "rhythm_tag": rhythm_tag(item),
                "use_status": use_status(item),
                "confidence_band": confidence_band(item),
                "review_priority": review_priority(item),
                "review_rank": review_rank(item),
                "action": item.action,
                "strategy": item.notes[0] if item.notes else "",
                "edit_suggestion": _edit_suggestion(item),
                "chosen": _candidate_payload(item.chosen),
                "alternatives": [_candidate_payload(candidate, primary=item.chosen, role="alternative") for candidate in item.alternatives],
                "external_search_links": item.external_search_links,
                "fallback_used": item.fallback_used,
                "notes": item.notes,
            }
            for item in result.segments
        ],
    }


def _candidate_payload(candidate, primary=None, role="chosen"):
    if not candidate:
        return None
    return {
        "source": candidate.source_type,
        "source_label": source_label(candidate),
        "selection_tag": selection_tag(candidate, primary=primary, role=role),
        "score": candidate.relevance_score,
        "level": candidate.match_level,
        "duration_fit": candidate.quality_signals.get("duration_fit"),
        "resolution": resolution_label(candidate),
        "orientation": orientation_label(candidate),
        "quality_tier": quality_tier(candidate),
        "crop_risk": crop_risk(candidate),
        "file": candidate.provider_meta.get("downloaded_path") or candidate.uri,
        "reason": candidate.reason,
        "chart_topic": candidate.provider_meta.get("chart_topic"),
        "chart_kind": candidate.provider_meta.get("chart_kind"),
        "license_type": candidate.license_type,
        "attribution_required": candidate.attribution_required,
        "source_page": candidate.source_page,
    }


def _edit_suggestion(item):
    segment = item.segment
    chosen = item.chosen
    if segment.visual_type == "skip":
        return "保留真人口播或开场镜头，不自动插入素材。"
    if segment.visual_type == "text_card":
        return "作为总结卡停留 2-3 秒，配合加粗标题或结论字幕。"
    if chosen and chosen.source_type == "data_card":
        topic = chosen.provider_meta.get("chart_topic")
        if topic == "health":
            return "把这张解释卡放在讲机制或作用时，建议停留 3-4 秒，便于观众读流程。"
        if topic == "economy":
            return "把这张经济解释卡放在因果说明句上，建议停留 3 秒左右，并搭配关键词字幕。"
        return "作为解释卡停留 3 秒左右，强调关系和结论。"
    if segment.visual_type == "stock_image":
        return "建议做轻微推拉或局部放大，避免静态画面过平。"
    if chosen and chosen.media_type == "video":
        return "建议裁出 2-4 秒核心镜头，避免长时间同一段素材。"
    return "建议按段落重点做轻量裁切，保持节奏紧凑。"
