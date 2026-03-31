from cmm.cache import FileCache
from cmm.config import ModelSettings
from cmm.models import MaterialCandidate, Segment
from cmm.scorer import SemanticScorer


def test_heuristic_fallback_prefers_semantic_overlap_and_media_fit(tmp_path):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )
    segment = Segment(
        id=1,
        text="植物会影响身体代谢。",
        visual_type="stock_image",
        scene_type="infographic",
        search_queries=["plants", "human metabolism", "health and nature"],
        keywords_en=["plants", "metabolism", "health"],
        visual_brief="plants and human body metabolism",
    )
    strong = MaterialCandidate(
        id="pixabay-image:good",
        source_type="pixabay",
        media_type="image",
        uri="https://example.com/good.jpg",
        source_page="https://pixabay.com/photos/herbs-health-body-123/",
        width=3072,
        height=4608,
        tags=["plants", "health", "body"],
        provider_meta={"title": "plants health body metabolism"},
    )
    weak = MaterialCandidate(
        id="pixabay-image:weak",
        source_type="pixabay",
        media_type="image",
        uri="https://example.com/weak.jpg",
        source_page="https://pixabay.com/photos/tea-leaves-drying-456/",
        width=3072,
        height=4608,
        tags=["tea", "leaves", "drying"],
        provider_meta={"title": "tea leaves drying in hands"},
    )

    payload = scorer._heuristic_fallback_scores(segment, [strong, weak])

    assert payload[0]["score"] > payload[1]["score"]
    assert "term overlap" in payload[0]["reason"]


def test_editorial_adjustment_penalizes_isolated_ingredient_for_infographic(tmp_path):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )
    segment = Segment(
        id=1,
        text="植物会影响身体代谢。",
        visual_type="stock_image",
        scene_type="infographic",
        search_queries=["plants affecting metabolism", "body metabolism"],
        keywords_en=["plants", "metabolism", "body"],
        visual_brief="illustration showing how plants affect body metabolism",
    )
    candidate = MaterialCandidate(
        id="pixabay-image:beetroot",
        source_type="pixabay",
        media_type="image",
        uri="https://example.com/beetroot.jpg",
        source_page="https://pixabay.com/photos/beetroot-vegetables-3434195/",
        width=6000,
        height=4000,
        tags=["beetroot", "vegetables", "food"],
        provider_meta={"title": "beetroot vegetables food metabolism"},
        relevance_score=0.90,
    )

    note = scorer._apply_editorial_adjustments(segment, candidate)

    assert candidate.relevance_score < 0.90
    assert "isolated ingredient" in note


def test_geo_adjustment_penalizes_non_china_asset_for_china_segment(tmp_path):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )
    segment = Segment(
        id=1,
        text="中国高铁和基础设施快速发展。",
        visual_type="stock_video",
        scene_type="b_roll",
        search_queries=["china high speed rail"],
        keywords_en=["china", "high speed rail", "infrastructure"],
        visual_brief="china rail and infrastructure growth",
    )
    candidate = MaterialCandidate(
        id="pixabay:foreign-train",
        source_type="pixabay",
        media_type="video",
        uri="https://example.com/foreign.mp4",
        source_page="https://pixabay.com/videos/id-205346/",
        tags=["high-speed train", "japan", "mount fuji"],
        provider_meta={"title": "high speed train japan mount fuji"},
        relevance_score=0.86,
    )

    note = scorer._apply_editorial_adjustments(segment, candidate)

    assert candidate.relevance_score < 0.86
    assert "outside the segment context" in note


def test_geo_adjustment_allows_explicit_comparison_country(tmp_path):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )
    segment = Segment(
        id=1,
        text="中国高铁与日本新干线常被放在一起比较，但中国高铁网络规模已大幅领先。",
        narrative_subject="china economy development story",
        context_statement="china and japan rail comparison: infrastructure scale and speed",
        context_tags=["china", "japan", "economy", "comparison story"],
        visual_type="stock_video",
        scene_type="b_roll",
        search_queries=["china japan high speed rail comparison"],
        keywords_en=["china", "japan", "high speed rail", "comparison"],
        visual_brief="china versus japan rail comparison",
    )
    candidate = MaterialCandidate(
        id="pexels:japan-rail",
        source_type="pexels",
        media_type="video",
        uri="https://example.com/japan-rail.mp4",
        source_page="https://example.com/japan-rail",
        tags=["japan", "high-speed train", "tokyo"],
        provider_meta={"title": "japan high speed rail comparison footage"},
        relevance_score=0.78,
    )

    note = scorer._apply_editorial_adjustments(segment, candidate)

    assert candidate.relevance_score >= 0.78
    assert "comparison geography" in note


def test_score_candidates_raises_when_judge_fails_and_fallback_is_disabled(tmp_path, monkeypatch):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )
    segment = Segment(id=1, text="城市经济活力。", visual_type="stock_video", scene_type="b_roll")
    candidate = MaterialCandidate(
        id="pexels:1",
        source_type="pexels",
        media_type="video",
        uri="https://example.com/clip.mp4",
        thumbnail_url="https://example.com/thumb.jpg",
    )

    async def failing_request_scores(self, segment, candidates):
        raise RuntimeError("judge down")

    monkeypatch.setattr(SemanticScorer, "_request_scores", failing_request_scores)

    try:
        __import__("asyncio").run(scorer.score_candidates(segment, [candidate]))
    except RuntimeError as exc:
        assert "judge down" in str(exc)
    else:
        raise AssertionError("Expected judge failure to raise when fallback is disabled.")


def test_score_candidates_uses_heuristic_when_explicitly_allowed(tmp_path, monkeypatch):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
        allow_fallback=True,
    )
    segment = Segment(
        id=1,
        text="植物会影响身体代谢。",
        visual_type="stock_image",
        scene_type="infographic",
        search_queries=["plants", "body metabolism"],
        keywords_en=["plants", "metabolism", "body"],
    )
    candidate = MaterialCandidate(
        id="pixabay:1",
        source_type="pixabay",
        media_type="image",
        uri="https://example.com/plant.jpg",
        thumbnail_url="https://example.com/thumb.jpg",
        tags=["plants", "body", "health"],
        provider_meta={"title": "plants body health"},
    )

    async def failing_request_scores(self, segment, candidates):
        raise RuntimeError("judge down")

    monkeypatch.setattr(SemanticScorer, "_request_scores", failing_request_scores)
    scored = __import__("asyncio").run(scorer.score_candidates(segment, [candidate]))

    assert len(scored) == 1
    assert scored[0].relevance_score > 0.0
    assert "Judge unavailable" in scored[0].reason
