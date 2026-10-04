import asyncio
import json

import httpx
import pytest

from cmm.cache import FileCache
from cmm.config import ModelSettings
from cmm.models import MaterialCandidate, Segment
from cmm.scorer import SemanticScorer


def chat_judge(tmp_path):
    return SemanticScorer(ModelSettings(provider="compatible", model="test", api_key="test-only", base_url="https://example.org/v1", max_retries=1), FileCache(str(tmp_path)))


def chat_candidate(identifier):
    return MaterialCandidate(id=identifier, source_type="commons", media_type="image", uri="https://example.org/" + identifier + ".jpg")


def test_chat_judge_retries_only_missing_candidates(tmp_path, monkeypatch):
    judge = chat_judge(tmp_path)
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        identifier = "asset-a" if len(requests) == 1 else "asset-b"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"scores": [{"id": identifier, "score": 0.72, "reason": "match"}]})}}]})

    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = asyncio.run(judge.score_candidates(Segment(id=1, text="city"), [chat_candidate("asset-a"), chat_candidate("asset-b")]))
    assert [candidate.id for candidate in result] == ["asset-a", "asset-b"]
    assert len(requests) == 2
    retry_content = json.dumps(requests[1]["messages"])
    assert "asset-b" in retry_content
    assert "asset-a" not in retry_content


@pytest.mark.parametrize("allow_fallback", [False, True])
def test_chat_judge_never_fabricates_or_caches_missing_scores(tmp_path, monkeypatch, allow_fallback):
    judge = chat_judge(tmp_path)
    judge.allow_fallback = allow_fallback
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"scores": []}'}}]})

    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    segment = Segment(id=1, text="city")
    candidate = chat_candidate("asset-a")
    if allow_fallback:
        result = asyncio.run(judge.score_candidates(segment, [candidate]))
        assert result[0].quality_signals["score_method"] == "heuristic"
    else:
        with pytest.raises(ValueError, match="no score"):
            asyncio.run(judge.score_candidates(segment, [candidate]))
    assert len(calls) == 2
    assert list((tmp_path / "judge").glob("*.json")) == []


def test_chat_judge_normalizes_numbered_scores_to_candidate_ids(tmp_path, monkeypatch):
    judge = chat_judge(tmp_path)
    payload = {"scores": [{"id": "2", "score": 0.75}, {"candidate_number": 1, "score": 0.7}]}

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = asyncio.run(judge.score_candidates(Segment(id=1, text="city"), [chat_candidate("asset-a"), chat_candidate("asset-b")]))
    assert [candidate.id for candidate in result] == ["asset-a", "asset-b"]
    assert [candidate.quality_signals["score_before_adjustments"] for candidate in result] == [0.7, 0.75]


@pytest.mark.parametrize("retry_status", [200, 403])
def test_chat_judge_preserves_valid_scores_when_only_missing_items_fall_back(tmp_path, monkeypatch, retry_status):
    judge = chat_judge(tmp_path)
    judge.allow_fallback = True
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            scores = [{"id": "asset-a", "score": 0.72, "reason": "model match"}]
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"scores": scores})}}]})
        return httpx.Response(retry_status, json={"choices": [{"message": {"content": '{"scores": []}'}}]})

    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    segment = Segment(id=1, text="city")
    first, missing = chat_candidate("asset-a"), chat_candidate("asset-b")
    result = asyncio.run(judge.score_candidates(segment, [first, missing]))
    assert result[0].quality_signals["score_method"] == "llm_judge"
    assert result[0].quality_signals["score_before_adjustments"] == 0.72
    assert result[1].quality_signals["score_method"] == "heuristic"
    assert judge.cache.has("judge", judge._cache_key(segment, [first]))
    assert not judge.cache.has("judge", judge._cache_key(segment, [missing]))
    assert len(calls) == 2


def test_chat_judge_prefers_exact_ids_over_conflicting_position_numbers(tmp_path, monkeypatch):
    judge = chat_judge(tmp_path)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        score = 0.8 if len(calls) == 1 else 0.7
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"scores": [{"id": "1", "score": score}]})}}]})

    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = asyncio.run(judge.score_candidates(Segment(id=1, text="city"), [chat_candidate("asset-a"), chat_candidate("1")]))
    assert [candidate.quality_signals["score_before_adjustments"] for candidate in result] == [0.7, 0.8]
    assert len(calls) == 2
    assert "asset-a" in json.dumps(calls[1]["messages"])


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


def test_deepseek_scorer_disables_image_input(tmp_path):
    scorer = SemanticScorer(
        ModelSettings(provider="deepseek", model="deepseek-v4-flash", api_key="x", base_url="https://api.deepseek.com"),
        FileCache(str(tmp_path / "cache")),
    )

    assert scorer._supports_image_input() is False


def test_openai_scorer_allows_image_input(tmp_path):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://api.openai.com/v1"),
        FileCache(str(tmp_path / "cache")),
        allow_vision=True,
    )

    assert scorer._supports_image_input() is True


def test_openai_scorer_disables_image_input_by_default(tmp_path):
    scorer = SemanticScorer(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="x", base_url="https://api.openai.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )

    assert scorer._supports_image_input() is False


def test_score_candidates_adds_candidate_bucket(tmp_path, monkeypatch):
    scorer = SemanticScorer(
        ModelSettings(provider="deepseek", model="deepseek-v4-flash", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )
    segment = Segment(id=1, text="城市经济活力。", visual_type="stock_video", scene_type="b_roll")
    candidate = MaterialCandidate(
        id="pexels:1",
        source_type="pexels",
        media_type="video",
        uri="https://example.com/clip.mp4",
        thumbnail_url="https://example.com/thumb.jpg",
        provider_meta={"title": "city skyline economy"},
    )

    async def fake_request_scores(self, segment, candidates):
        return [{"id": candidates[0].id, "score": 0.66, "reason": "Usable match."}]

    monkeypatch.setattr(SemanticScorer, "_request_scores", fake_request_scores)
    scored = __import__("asyncio").run(scorer.score_candidates(segment, [candidate]))

    assert scored[0].provider_meta["candidate_bucket"] == "ready"


def test_score_candidates_records_transparent_score_details(tmp_path, monkeypatch):
    scorer = SemanticScorer(
        ModelSettings(provider="deepseek", model="deepseek-v4-flash", api_key="x", base_url="https://example.com/v1"),
        FileCache(str(tmp_path / "cache")),
    )
    segment = Segment(id=1, text="城市经济活力。", visual_type="stock_video", scene_type="b_roll")
    candidate = MaterialCandidate(
        id="pexels:1",
        source_type="pexels",
        media_type="video",
        uri="https://example.com/clip.mp4",
        thumbnail_url="https://example.com/thumb.jpg",
        width=1080,
        height=1920,
        duration=8,
        provider_meta={"title": "city skyline economy"},
    )

    async def fake_request_scores(self, segment, candidates):
        return [{"id": candidates[0].id, "score": 0.72, "reason": "Good city economy fit."}]

    monkeypatch.setattr(SemanticScorer, "_request_scores", fake_request_scores)
    scored = __import__("asyncio").run(scorer.score_candidates(segment, [candidate]))
    details = scored[0].quality_signals

    assert details["score_method"] == "llm_judge"
    assert details["score_before_adjustments"] == 0.72
    assert details["score_after_adjustments"] == scored[0].relevance_score
    assert details["score_breakdown"]["semantic"] == 0.72
    assert details["technical_score"] > 0
    assert "Good city economy fit." in details["score_notes"][0]
