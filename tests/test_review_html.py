import json
from pathlib import Path

from cmm.models import AnalysisResult, MatchResult, MatchSummary, MaterialCandidate, Segment, SegmentMatch
from cmm.outputs.writer import write_match_outputs


def test_write_match_outputs_includes_static_review_html_and_score_fields(tmp_path: Path):
    segment = Segment(
        id=1,
        text="城市车流展现经济活力。",
        segment_role="example",
        visual_type="stock_video",
        scene_type="b_roll",
        search_queries=["city traffic economy"],
    )
    candidate = MaterialCandidate(
        id="pexels:1",
        source_type="pexels",
        media_type="video",
        uri="https://example.com/video.mp4",
        source_page="https://example.com/page",
        relevance_score=0.82,
        match_level="approx",
        reason="Good traffic match.",
        width=1080,
        height=1920,
        quality_signals={
            "score_method": "llm_judge",
            "score_breakdown": {"semantic": 0.82, "technical": 0.55, "aspect_fit": 1.0, "final": 0.82},
            "score_notes": ["Good traffic match.", "technical fit 0.55"],
            "score_before_adjustments": 0.82,
            "score_after_adjustments": 0.82,
            "semantic_score": 0.82,
            "technical_score": 0.55,
            "aspect_fit": 1.0,
        },
        provider_meta={"title": "City traffic", "candidate_bucket": "ready", "score_method": "llm_judge"},
    )
    result = MatchResult(
        created_at="2026-07-01T00:00:00+00:00",
        total_segments=1,
        analysis=AnalysisResult(segments=[segment]),
        segments=[
            SegmentMatch(
                segment=segment,
                chosen=candidate,
                alternatives=[],
                external_search_links=[{"name": "vjshi", "url": "https://www.vjshi.com/search?wd=city"}],
                notes=["策略：该段有明确可拍场景，优先匹配真实实景视频素材。"],
            )
        ],
        match_summary=MatchSummary(approximate=1),
        output_dir=str(tmp_path),
    )

    write_match_outputs(result, str(tmp_path))

    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    overview = (tmp_path / "segments_overview.csv").read_text(encoding="utf-8")
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8-sig")

    assert "ScriptMate Review" in html
    assert "城市车流展现经济活力" in html
    assert "semantic=0.82" in html
    assert "https://www.vjshi.com/search?wd=city" in html
    assert manifest["segments"][0]["chosen"]["score_method"] == "llm_judge"
    assert manifest["segments"][0]["chosen"]["score_breakdown"]["semantic"] == 0.82
    assert "semantic_score,technical_score,local_match_score,aspect_fit,score_method,score_notes" in overview
    assert "评分细项：semantic=0.82" in summary
