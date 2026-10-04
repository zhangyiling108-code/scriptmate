import asyncio
import json

import httpx
import pytest
from PIL import Image

from cmm.cache import FileCache
from cmm.config import ModelSettings, Settings
from cmm.models import MaterialCandidate, Segment, SegmentMatch
from cmm.outputs.labels import use_status
from cmm.pipeline import _is_candidate_acceptable
from cmm.scorer import PrefilteredScorer, SemanticScorer


def asset(identifier="fish", media="image", thumb="https://example.org/fish.jpg"):
    return MaterialCandidate(id=identifier, source_type="commons", media_type=media,
                             uri="https://example.org/fish." + ("jpg" if media == "image" else "mp4"),
                             thumbnail_url=thumb, provider_meta={"title": "Sturgeon"})


def visual_scorer(tmp_path):
    return SemanticScorer(ModelSettings(provider="deepseek", model="deepseek-flash", api_key="test",
                                        supports_vision=True), FileCache(str(tmp_path)), allow_vision=True)


def mock_scores(monkeypatch, items, requests):
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "vision-test", "choices": [{"message": {
            "content": json.dumps({"scores": items})}}]})
    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_visual_evidence_is_per_asset_not_per_model(tmp_path, monkeypatch):
    calls = []
    mock_scores(monkeypatch, [{"id": "fish", "score": .91, "visible_evidence": "A long fish with bony scutes."},
                             {"id": "clip", "score": .95, "visible_evidence": "Invented from title."}], calls)
    scored = asyncio.run(visual_scorer(tmp_path).score_candidates(
        Segment(id=1, text="鲟鱼"), [asset(), asset("clip", "video", "")]))
    assert scored[0].quality_signals["evidence_scope"] == "image"
    assert scored[0].quality_signals["visual_observation"] == "A long fish with bony scutes."
    assert scored[0].quality_signals["judge_details"]["model"] == "vision-test"
    assert scored[1].quality_signals["evidence_scope"] == "metadata"
    assert scored[1].quality_signals["score_method"] != "vision_judge"
    assert use_status(SegmentMatch(segment=Segment(id=1, text="fish"), chosen=scored[1])) == "review"
    assert len([p for p in calls[0]["messages"][1]["content"] if p["type"] == "image_url"]) == 1


def test_high_metadata_score_cannot_rescue_visual_mismatch(tmp_path, monkeypatch):
    calls = []
    mock_scores(monkeypatch, [{"id": "fish", "score": .1, "visible_evidence": "A goldfish, not a sturgeon."}], calls)
    class MetadataScorer:
        async def score_candidates(self, segment, candidates, batch_size=4):
            for candidate in candidates:
                candidate.relevance_score = .99
                candidate.quality_signals["judge_details"] = {"model": "jev-test", "evidence": "metadata"}
            return candidates
    scorer = PrefilteredScorer(MetadataScorer(), visual_scorer(tmp_path), limit=12)
    candidate = asyncio.run(scorer.score_candidates(Segment(id=1, text="鲟鱼"), [asset()]))[0]
    assert candidate.relevance_score == .1
    assert candidate.quality_signals["metadata_score"] == .99
    assert candidate.quality_signals["metadata_judge_details"]["model"] == "jev-test"
    assert not _is_candidate_acceptable(Segment(id=1, text="fish"), candidate, Settings().matching, Settings())


def test_thumbnail_and_metadata_never_pass_visual_gate():
    settings = Settings(judge={"require_visual_evidence": True})
    for scope in ["metadata", "video_thumbnail", "unverified"]:
        candidate = asset(media="video" if scope == "video_thumbnail" else "image")
        candidate.relevance_score = .99
        candidate.quality_signals["evidence_scope"] = scope
        assert not _is_candidate_acceptable(Segment(id=1, text="fish"), candidate, settings.matching, settings)
    candidate.quality_signals["evidence_scope"] = "image"
    assert _is_candidate_acceptable(Segment(id=1, text="fish"), candidate, settings.matching, settings)


def test_visual_score_without_observation_fails_closed(tmp_path, monkeypatch):
    calls = []
    mock_scores(monkeypatch, [{"id": "fish", "score": .99}], calls)
    with pytest.raises(ValueError, match="visible evidence"):
        asyncio.run(visual_scorer(tmp_path).score_candidates(Segment(id=1, text="fish"), [asset()]))


def test_inline_images_are_encoded_and_invalid_images_require_review(tmp_path, monkeypatch):
    import io
    image = Image.new("RGB", (24, 24), "red")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    calls = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, content=stream.getvalue())
        body = json.loads(request.content)
        calls.append(body)
        content = body["messages"][1]["content"]
        assert next(p for p in content if p["type"] == "image_url")["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"scores": [
            {"id": "fish", "score": .7, "visible_evidence": "A red field."}]})}}]})
    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    scorer = visual_scorer(tmp_path)
    scorer.settings.image_transport = "inline"
    result = asyncio.run(scorer.score_candidates(Segment(id=1, text="fish"), [asset()]))
    assert result[0].quality_signals["evidence_scope"] == "image"
    assert len(calls) == 1

    def invalid_handler(request):
        if request.method == "GET":
            return httpx.Response(200, content=b"not an image")
        body = json.loads(request.content)
        assert all(part["type"] != "image_url" for part in body["messages"][1]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"scores": [
            {"id": "invalid", "score": .99, "visible_evidence": "A fabricated fish."}]})}}]})
    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(invalid_handler)))
    result = asyncio.run(scorer.score_candidates(Segment(id=2, text="fish"), [asset("invalid")]))
    assert result[0].quality_signals["evidence_scope"] == "metadata"
    assert result[0].quality_signals["visual_input_error"] == "UnidentifiedImageError"
    assert not result[0].quality_signals["visual_observation"]
    assert not scorer.cache.load_json("judge", scorer._cache_key(Segment(id=2, text="fish"), [asset("invalid")]))
    assert use_status(SegmentMatch(segment=Segment(id=2, text="fish"), chosen=result[0])) == "review"


def test_prefilter_bounds_visual_requests_and_keeps_best_metadata_order():
    class MetadataScorer:
        async def score_candidates(self, segment, candidates, batch_size=4):
            for number, candidate in enumerate(candidates):
                candidate.relevance_score = number / 10
            return candidates
    seen = []
    class FinalScorer:
        async def score_candidates(self, segment, candidates, batch_size=4):
            seen.extend(candidate.id for candidate in candidates)
            return candidates
    candidates = [asset(str(number)) for number in range(8)]
    result = asyncio.run(PrefilteredScorer(MetadataScorer(), FinalScorer(), limit=3).score_candidates(
        Segment(id=1, text="fish"), candidates))
    assert seen == ["7", "6", "5"]
    assert len(result) == 3
    assert result[0].quality_signals["metadata_score"] == .7


def test_unavailable_preview_does_not_block_other_images(tmp_path, monkeypatch):
    import io
    stream = io.BytesIO()
    Image.new("RGB", (24, 24), "blue").save(stream, format="PNG")
    def handler(request):
        if request.method == "GET":
            return httpx.Response(403 if "blocked" in request.url.path else 200,
                                  content=stream.getvalue())
        body = json.loads(request.content)
        parts = body["messages"][1]["content"]
        assert len([part for part in parts if part["type"] == "image_url"]) == 1
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"scores": [
            {"id": "fish", "score": .1, "visible_evidence": "A plain blue field."},
            {"id": "blocked", "score": .99, "visible_evidence": "An invented sturgeon."}]})}}]})
    monkeypatch.setattr("cmm.scorer.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    scorer = visual_scorer(tmp_path)
    scorer.settings.image_transport = "inline"
    segment = Segment(id=1, text="fish")
    candidates = [asset(), asset("blocked", thumb="https://example.org/blocked.jpg")]
    scored = asyncio.run(scorer.score_candidates(segment, candidates))
    assert scored[0].quality_signals["evidence_scope"] == "image"
    assert scored[1].quality_signals["evidence_scope"] == "metadata"
    assert scored[1].quality_signals["visual_input_error"] == "HTTPStatusError: 403"
    assert scored[1].quality_signals["visual_score"] is None
    assert scorer.cache.load_json("judge", scorer._cache_key(segment, [candidates[0]]))
    assert scorer.cache.load_json("judge", scorer._cache_key(segment, [candidates[1]])) is None


def test_video_cover_is_observed_but_never_accepted_as_full_clip(tmp_path, monkeypatch):
    calls = []
    mock_scores(monkeypatch, [{"id": "clip", "score": .99, "visible_evidence": "A sturgeon in one still frame."}], calls)
    candidate = asyncio.run(visual_scorer(tmp_path).score_candidates(
        Segment(id=1, text="fish"), [asset("clip", "video")]))[0]
    assert candidate.quality_signals["evidence_scope"] == "video_thumbnail"
    assert candidate.quality_signals["visual_observation"]
    settings = Settings(judge={"require_visual_evidence": True})
    assert not _is_candidate_acceptable(Segment(id=1, text="fish"), candidate, settings.matching, settings)
    assert use_status(SegmentMatch(segment=Segment(id=1, text="fish"), chosen=candidate)) == "review"


def test_prefilter_credentials_do_not_borrow_judge_or_planner_keys(tmp_path, monkeypatch):
    for name in ["PREFILTER_MODEL_PROVIDER", "PREFILTER_MODEL_API_KEY", "TYPESAFE_API_KEY"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "planner-key")
    monkeypatch.setenv("JUDGE_MODEL_API_KEY", "judge-key")
    path = tmp_path / "config.toml"
    path.write_text('[prefilter_model]\nprovider = "typesafe"\n')
    settings = Settings.from_file(str(path))
    assert settings.prefilter_model.api_key == ""
    monkeypatch.setenv("TYPESAFE_API_KEY", "jev-test-key")
    assert Settings.from_file(str(path)).prefilter_model.api_key == "jev-test-key"
