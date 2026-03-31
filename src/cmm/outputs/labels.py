from __future__ import annotations

from typing import Optional

from cmm.models import MaterialCandidate, SegmentMatch


def source_label(candidate: Optional[MaterialCandidate]) -> str:
    if not candidate:
        return ""
    if candidate.source_type == "data_card":
        topic = candidate.provider_meta.get("chart_topic", "general")
        kind = candidate.provider_meta.get("chart_kind", "bar")
        return "generated.data_card.{0}.{1}".format(topic, kind)
    if candidate.source_type == "text_card":
        return "generated.text_card"
    if candidate.source_type in {"pexels", "pixabay", "local", "generic"}:
        media = candidate.media_type or "asset"
        return "{0}.{1}".format(candidate.source_type, media)
    return candidate.source_type


def selection_tag(candidate: MaterialCandidate, primary: Optional[MaterialCandidate] = None, role: str = "chosen") -> str:
    if role != "alternative":
        return "primary"
    if primary is None:
        return "manual_candidate"
    if candidate.source_type in {"data_card", "text_card"}:
        return "explainer_backup"
    if candidate.source_type != primary.source_type and candidate.media_type != primary.media_type:
        return "diverse_backup"
    if candidate.source_type != primary.source_type:
        return "source_backup"
    if candidate.media_type != primary.media_type:
        return "media_backup"
    return "same_lane_backup"


def duration_fit(candidate: Optional[MaterialCandidate]) -> str:
    if candidate is None:
        return ""
    fit = candidate.quality_signals.get("duration_fit")
    if fit in (None, ""):
        return ""
    return "{0:.2f}".format(float(fit))


def resolution_label(candidate: Optional[MaterialCandidate]) -> str:
    if not candidate:
        return ""
    width = candidate.width or 0
    height = candidate.height or 0
    if not width or not height:
        return ""
    return "{0}x{1}".format(width, height)


def orientation_label(candidate: Optional[MaterialCandidate]) -> str:
    if not candidate:
        return ""
    orientation = candidate.quality_signals.get("orientation")
    if orientation:
        return str(orientation)
    width = candidate.width or 0
    height = candidate.height or 0
    if not width or not height:
        return ""
    return "vertical" if height >= width else "horizontal"


def quality_tier(candidate: Optional[MaterialCandidate]) -> str:
    if not candidate:
        return ""
    if candidate.source_type in {"data_card", "text_card"}:
        return "generated"
    width = candidate.width or 0
    height = candidate.height or 0
    orientation = orientation_label(candidate)
    fit = candidate.quality_signals.get("duration_fit")
    if orientation == "vertical" and height >= 1920 and fit is not None and float(fit) >= 0.85:
        return "ready_vertical"
    if orientation == "vertical" and height >= 1080:
        return "usable_vertical"
    if height >= 1080 or width >= 1080:
        return "usable_hd"
    return "review_asset"


def crop_risk(candidate: Optional[MaterialCandidate]) -> str:
    if not candidate:
        return ""
    if candidate.source_type in {"data_card", "text_card"}:
        return "none"
    width = candidate.width or 0
    height = candidate.height or 0
    if not width or not height:
        return ""
    if height >= width:
        return "low"
    aspect = width / height if height else 0
    if aspect >= 1.7:
        return "high"
    return "medium"


def asset_class(item: SegmentMatch) -> str:
    segment = item.segment
    chosen = item.chosen
    if segment.visual_type == "skip":
        return "host_placeholder"
    if segment.visual_type == "text_card":
        return "summary_card"
    if chosen and chosen.source_type == "data_card":
        topic = chosen.provider_meta.get("chart_topic", "general")
        kind = chosen.provider_meta.get("chart_kind", "bar")
        return "{0}_{1}_card".format(topic, kind)
    if chosen and chosen.source_type == "text_card":
        return "text_card"
    if segment.visual_type == "stock_image":
        return "explanatory_image"
    if chosen and chosen.media_type == "video":
        return "broll_video"
    if chosen and chosen.media_type == "image":
        return "supporting_image"
    return "unmatched"


def rhythm_tag(item: SegmentMatch) -> str:
    segment = item.segment
    chosen = item.chosen
    if segment.visual_type == "skip":
        return "intro_hold"
    if segment.visual_type == "text_card":
        return "summary_pause"
    if chosen and chosen.source_type == "data_card":
        return "explain_pause"
    if segment.visual_type == "stock_image":
        return "support_hold"
    if chosen and chosen.media_type == "video":
        return "motion_cutaway"
    if chosen and chosen.media_type == "image":
        return "visual_hold"
    return "manual_review"


def use_status(item: SegmentMatch) -> str:
    segment = item.segment
    chosen = item.chosen
    if segment.visual_type == "skip":
        return "host_only"
    if chosen is None:
        return "review"
    if chosen.source_type == "data_card":
        return "prefer_explainer"
    if chosen.source_type == "text_card":
        return "ready_summary"
    if item.fallback_used or chosen.match_level == "generic":
        return "review"
    if chosen.relevance_score >= 0.85:
        return "ready"
    if chosen.relevance_score >= 0.7:
        return "usable"
    return "review"


def confidence_band(item: SegmentMatch) -> str:
    chosen = item.chosen
    status = use_status(item)
    if status == "host_only":
        return "manual"
    if chosen is None:
        return "low"
    if chosen.source_type in {"data_card", "text_card"}:
        return "high"
    if chosen.relevance_score >= 0.85:
        return "high"
    if chosen.relevance_score >= 0.7:
        return "medium"
    return "low"


def review_priority(item: SegmentMatch) -> str:
    status = use_status(item)
    if status in {"ready", "ready_summary", "host_only"}:
        return "none"
    if status == "prefer_explainer":
        return "low"
    if status == "usable":
        return "medium"
    if item.fallback_used:
        return "high"
    if item.chosen is None:
        return "critical"
    return "high"


def review_rank(item: SegmentMatch) -> int:
    return {
        "none": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }.get(review_priority(item), 0)
