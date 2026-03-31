from __future__ import annotations

from collections import Counter

from cmm.models import MatchResult
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


def build_report(result: MatchResult) -> str:
    source_counts = Counter(
        item.chosen.source_type for item in result.segments if item.chosen is not None and item.segment.visual_type != "skip"
    )
    visual_counts = Counter(item.segment.visual_type for item in result.segments)
    asset_counts = Counter(asset_class(item) for item in result.segments)
    rhythm_counts = Counter(rhythm_tag(item) for item in result.segments)
    use_counts = Counter(use_status(item) for item in result.segments)
    confidence_counts = Counter(confidence_band(item) for item in result.segments)
    review_counts = Counter(review_priority(item) for item in result.segments)
    quality_counts = Counter(quality_tier(item.chosen) for item in result.segments if quality_tier(item.chosen))
    review_queue = sorted(
        (item for item in result.segments if review_rank(item) > 0),
        key=lambda item: (-review_rank(item), _confidence_sort_key(confidence_band(item)), item.segment.id),
    )
    lines = [
        "# ScriptMate 匹配报告",
        "",
        "## 概览",
        "- 总段落：{0}".format(result.total_segments),
        "- 分析模式：{0}".format("本地规则降级" if result.analysis.overall_style.startswith("heuristic fallback") else "模型分析"),
        "- 精确匹配：{0}".format(result.match_summary.exact),
        "- 近似匹配：{0}".format(result.match_summary.approximate),
        "- 泛化真实素材：{0}".format(result.match_summary.generic_real),
        "- 生成 fallback：{0}".format(result.match_summary.generated),
        "- 跳过：{0}".format(result.match_summary.skipped),
        "",
        "## 素材分布",
        "- 视觉类型：{0}".format(_format_counter(visual_counts)),
        "- 推荐来源：{0}".format(_format_counter(source_counts)),
        "- 资产类别：{0}".format(_format_counter(asset_counts)),
        "- 节奏标签：{0}".format(_format_counter(rhythm_counts)),
        "- 可用建议：{0}".format(_format_counter(use_counts)),
        "- 置信区间：{0}".format(_format_counter(confidence_counts)),
        "- 复核优先级：{0}".format(_format_counter(review_counts)),
        "- 质量标签：{0}".format(_format_counter(quality_counts)),
        "",
        "## 复核队列",
        "",
    ]
    if review_queue:
        for item in review_queue:
            lines.append(
                "- {0}. [{1}/{2}] {3}".format(
                    item.segment.id,
                    review_priority(item),
                    confidence_band(item),
                    _review_queue_line(item),
                )
            )
    else:
        lines.append("- 无需人工复核")
    lines.extend(["", "## 节奏总览", ""])
    for item in result.segments:
        lines.append("- {0}. {1}".format(item.segment.id, _timeline_line(item)))
    lines.extend(["", "## 逐段详情", ""])
    for item in result.segments:
        lines.append("### 段落 {0} — {1}".format(item.segment.id, item.segment.visual_type))
        lines.append("> \"{0}\"".format(item.segment.text))
        if item.segment.narrative_subject:
            lines.append("- 叙事主语：{0}".format(item.segment.narrative_subject))
        if item.segment.context_statement:
            lines.append("- 上下文：{0}".format(item.segment.context_statement))
        if item.segment.context_tags:
            lines.append("- 约束标签：{0}".format(" / ".join(item.segment.context_tags)))
        if item.notes:
            lines.append("- 策略：{0}".format(item.notes[0].replace("策略：", "").strip()))
        if item.external_search_links:
            external_summary = "、".join(
                "{0}: {1}".format(link.get("name", "external"), link.get("url", ""))
                for link in item.external_search_links[:4]
            )
            lines.append("- 扩展素材库：{0}".format(external_summary))
        lines.append("- 建议：{0}".format(use_status(item)))
        lines.append("- 置信：{0} / 复核优先级：{1}".format(confidence_band(item), review_priority(item)))
        duration_fit_value = duration_fit(item.chosen)
        if duration_fit_value:
            lines.append("- 时长贴合度：{0}".format(duration_fit_value))
        resolution = resolution_label(item.chosen)
        orientation = orientation_label(item.chosen)
        quality = quality_tier(item.chosen)
        crop = crop_risk(item.chosen)
        if resolution or orientation:
            lines.append("- 规格：{0}{1}".format(
                resolution or "未知分辨率",
                " / {0}".format(orientation) if orientation else "",
            ))
        if quality:
            lines.append("- 质量标签：{0}".format(quality))
        if crop:
            lines.append("- 裁切风险：{0}".format(crop))
        if item.action == "skip":
            lines.append("- 跳过：口播/开场保留给人工处理")
        elif item.chosen:
            chart_meta = ""
            if item.chosen.source_type == "data_card":
                chart_kind = item.chosen.provider_meta.get("chart_kind")
                chart_topic = item.chosen.provider_meta.get("chart_topic")
                if chart_kind or chart_topic:
                    chart_meta = " [{0}{1}]".format(
                        chart_topic or "general",
                        "/{0}".format(chart_kind) if chart_kind else "",
                    )
            lines.append(
                "- 推荐：{0} ({1}, {2:.2f})".format(
                    (item.chosen.reason or item.chosen.provider_meta.get("title", item.chosen.uri)) + chart_meta,
                    item.chosen.source_type,
                    item.chosen.relevance_score,
                )
            )
            lines.append("- 直链：{0}".format(item.chosen.uri))
            if item.chosen.source_page:
                lines.append("- 来源页：{0}".format(item.chosen.source_page))
            if item.alternatives:
                alternatives = ", ".join(
                    "{0}/{1} ({2:.2f})".format(
                        source_label(candidate),
                        selection_tag(candidate, item.chosen, role="alternative"),
                        candidate.relevance_score,
                    )
                    for candidate in item.alternatives
                )
                lines.append("- 备选：{0}".format(alternatives))
                for index, candidate in enumerate(item.alternatives, start=1):
                    lines.append("  - 备选{0}链接：{1}".format(index, candidate.uri))
                    if candidate.source_page:
                        lines.append("  - 备选{0}来源页：{1}".format(index, candidate.source_page))
            if item.fallback_used:
                lines.append("- 备注：该段使用了 fallback 策略")
        else:
            lines.append("- 未匹配到可用素材")
            if item.alternatives:
                alternatives = ", ".join(
                    "{0}/{1} ({2:.2f})".format(
                        source_label(candidate),
                        selection_tag(candidate, None, role="alternative"),
                        candidate.relevance_score,
                    )
                    for candidate in item.alternatives
                )
                lines.append("- 待选链接：{0}".format(alternatives))
                for index, candidate in enumerate(item.alternatives, start=1):
                    lines.append("  - 候选{0}直链：{1}".format(index, candidate.uri))
                    if candidate.source_page:
                        lines.append("  - 候选{0}来源页：{1}".format(index, candidate.source_page))
        for note in item.notes[1:] if len(item.notes) > 1 else []:
            lines.append("- 说明：{0}".format(note))
        lines.append("")
    if result.warnings:
        lines.extend(["## Warnings", ""])
        lines.extend("- {0}".format(item) for item in result.warnings)
        lines.append("")
    if result.errors:
        lines.extend(["## Errors", ""])
        lines.extend("- {0}".format(item) for item in result.errors)
        lines.append("")
    return "\n".join(lines)


def _format_counter(counter: Counter) -> str:
    if not counter:
        return "无"
    return "、".join("{0} x{1}".format(key, value) for key, value in counter.items())


def _confidence_sort_key(band: str) -> int:
    return {
        "low": 0,
        "manual": 1,
        "medium": 2,
        "high": 3,
    }.get(band, 0)


def _review_queue_line(item) -> str:
    chosen = item.chosen
    source = source_label(chosen) if chosen else "unmatched"
    strategy = item.notes[0].replace("策略：", "").strip() if item.notes else "建议人工复核"
    quality = quality_tier(chosen)
    suffix = " | {0}".format(quality) if quality else ""
    return "{0} -> {1}{2} | {3}".format(item.segment.segment_role, source, suffix, strategy)


def _timeline_line(item) -> str:
    role = item.segment.segment_role
    visual_type = item.segment.visual_type
    item_asset_class = asset_class(item)
    item_rhythm_tag = rhythm_tag(item)
    if item.action == "skip":
        return "{0} | {1} | {2} | {3} | {4} | 开场/口播保留".format(
            role, visual_type, item_asset_class, item_rhythm_tag, use_status(item)
        )
    if not item.chosen:
        return "{0} | {1} | {2} | {3} | {4} | 未匹配".format(
            role, visual_type, item_asset_class, item_rhythm_tag, use_status(item)
        )

    source = item.chosen.source_type
    score = "{0:.2f}".format(item.chosen.relevance_score)
    tag = ""
    if source == "data_card":
        topic = item.chosen.provider_meta.get("chart_topic")
        kind = item.chosen.provider_meta.get("chart_kind")
        if topic or kind:
            tag = " [{0}{1}]".format(topic or "general", "/{0}".format(kind) if kind else "")
    elif source in {"pexels", "pixabay", "local", "generic"}:
        title = item.chosen.provider_meta.get("title")
        if title:
            tag = " [{0}]".format(title)
    return "{0} | {1} | {2} | {3} | {4} | {5}{6} | {7}".format(
        role,
        visual_type,
        item_asset_class,
        item_rhythm_tag,
        use_status(item),
        source,
        tag,
        score,
    )
