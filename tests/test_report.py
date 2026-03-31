from cmm.models import AnalysisResult, MatchResult, MatchSummary, MaterialCandidate, Segment, SegmentMatch
from cmm.outputs.report import build_report


def test_build_report_includes_distribution_and_timeline_overview():
    result = MatchResult(
        created_at="2026-03-30T00:00:00+00:00",
        total_segments=3,
        analysis=AnalysisResult(
            segments=[
                Segment(id=1, text="大家好", segment_role="hook", visual_type="skip", scene_type="talking_head"),
                Segment(id=2, text="经济增长会影响消费。", segment_role="claim", visual_type="data_card", scene_type="infographic"),
                Segment(id=3, text="城市车流展现活力。", segment_role="example", visual_type="stock_video", scene_type="b_roll"),
            ],
            overall_style="clean documentary",
            target_aspect="9:16",
        ),
        segments=[
            SegmentMatch(
                segment=Segment(id=1, text="大家好", segment_role="hook", visual_type="skip", scene_type="talking_head"),
                action="skip",
                notes=["策略：该段保留给口播开场或人工镜头，不自动匹配素材。"],
            ),
            SegmentMatch(
                segment=Segment(id=2, text="经济增长会影响消费。", segment_role="claim", visual_type="data_card", scene_type="infographic"),
                action="generated",
                chosen=MaterialCandidate(
                    id="data_card:2",
                    source_type="data_card",
                    media_type="image",
                    uri="/tmp/chart.png",
                    relevance_score=0.88,
                    match_level="exact",
                    reason="Generated explainer card.",
                    provider_meta={"chart_topic": "economy", "chart_kind": "causal"},
                ),
                notes=["策略：该段属于抽象解释，优先生成 economy/causal 解释卡。"],
            ),
            SegmentMatch(
                segment=Segment(id=3, text="城市车流展现活力。", segment_role="example", visual_type="stock_video", scene_type="b_roll"),
                action="selected",
                chosen=MaterialCandidate(
                    id="pixabay:3",
                    source_type="pixabay",
                    media_type="video",
                    uri="https://example.com/video.mp4",
                    relevance_score=0.81,
                    match_level="exact",
                    reason="Busy city traffic match.",
                    width=1080,
                    height=1920,
                    quality_signals={"duration_fit": 0.85},
                    provider_meta={"title": "City traffic"},
                ),
                alternatives=[
                    MaterialCandidate(
                        id="data_card:4",
                        source_type="data_card",
                        media_type="image",
                        uri="/tmp/alt-chart.png",
                        relevance_score=0.72,
                        match_level="approx",
                        reason="Backup explainer card.",
                        provider_meta={"chart_topic": "economy", "chart_kind": "causal"},
                    ),
                    MaterialCandidate(
                        id="pexels:5",
                        source_type="pexels",
                        media_type="video",
                        uri="https://example.com/alt.mp4",
                        relevance_score=0.75,
                        match_level="approx",
                        reason="Alternate city scene.",
                    ),
                ],
                notes=["策略：该段有明确可拍场景，优先匹配真实实景视频素材。"],
            ),
        ],
        match_summary=MatchSummary(exact=1, generated=1, skipped=1),
        output_dir="/tmp/output",
    )

    report = build_report(result)

    assert "## 素材分布" in report
    assert "视觉类型：" in report
    assert "推荐来源：" in report
    assert "资产类别：" in report
    assert "节奏标签：" in report
    assert "可用建议：" in report
    assert "置信区间：" in report
    assert "复核优先级：" in report
    assert "质量标签：" in report
    assert "## 复核队列" in report
    assert "## 节奏总览" in report
    assert "- 2. claim | data_card | economy_causal_card | explain_pause | prefer_explainer | data_card [economy/causal] | 0.88" in report
    assert "- 3. example | stock_video | broll_video | motion_cutaway | usable | pixabay [City traffic] | 0.81" in report
    assert "推荐来源：data_card x1、pixabay x1" in report
    assert "资产类别：host_placeholder x1、economy_causal_card x1、broll_video x1" in report
    assert "可用建议：host_only x1、prefer_explainer x1、usable x1" in report
    assert "置信区间：manual x1、high x1、medium x1" in report
    assert "复核优先级：none x1、low x1、medium x1" in report
    assert "质量标签：generated x1、ready_vertical x1" in report
    assert "generated.data_card.economy.causal/explainer_backup (0.72)" in report
    assert "pexels.video/source_backup (0.75)" in report
    assert "- 3. [medium/medium] example -> pixabay.video | ready_vertical | 该段有明确可拍场景，优先匹配真实实景视频素材。" in report
    assert "- 2. [low/high] claim -> generated.data_card.economy.causal | generated | 该段属于抽象解释，优先生成 economy/causal 解释卡。" in report
    assert "- 建议：prefer_explainer" in report
    assert "- 置信：high / 复核优先级：low" in report
    assert "- 置信：medium / 复核优先级：medium" in report
    assert "- 直链：https://example.com/video.mp4" in report
    assert "  - 备选1链接：/tmp/alt-chart.png" in report
    assert "  - 备选2链接：https://example.com/alt.mp4" in report
    assert "- 时长贴合度：0.85" in report
    assert "- 规格：1080x1920 / vertical" in report
    assert "- 质量标签：ready_vertical" in report
    assert "- 裁切风险：low" in report
