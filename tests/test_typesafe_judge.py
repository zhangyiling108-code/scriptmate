import asyncio
import json

import httpx
import pytest
from typer.testing import CliRunner

from cmm.cache import FileCache
from cmm.cli import app
from cmm.config import ModelSettings, Settings
from cmm.library.matcher import LocalLibraryMatcher
from cmm.models import AnalysisResult, LibraryAsset, MaterialCandidate, MatchInput, MatchResult, MatchSummary, Segment, SegmentMatch
from cmm.pipeline import match_script
from cmm.outputs.writer import write_match_outputs
from cmm.scorer import SemanticScorer
from cmm.typesafe_judge import CRITERIA


def candidate(identifier="asset:id"):
    return MaterialCandidate(
        id=identifier, source_type="commons", media_type="image", uri="https://example.org/asset.jpg",
        tags=["urban skyline"], width=1080, height=1920,
        provider_meta={"title": "City skyline", "description": "Urban architecture", "query": "UNVERIFIED_QUERY"},
    )


def segment():
    return Segment(id=1, text="城市发展", visual_type="stock_image", visual_brief="urban development")


def judge(tmp_path, **kwargs):
    return SemanticScorer(ModelSettings(provider="typesafe", api_key="test-only-key"), FileCache(str(tmp_path / "cache")), **kwargs)


def answer():
    return {
        "type": "score", "score": 3.2, "confidence": 0.91,
        "legend": {str(i): text for i, text in enumerate(CRITERIA)},
        "probabilities": {"0": 0, "1": 0, "2": 0, "3": 0.8, "4": 0.2},
    }


def response(body):
    return {
        "model": "jev-contract-test", "answers": {name: answer() for name in body["questions"]},
        "usage": {"input_tokens": 200, "output_tokens": 0},
    }


def mock_client(monkeypatch, handler):
    monkeypatch.setattr("cmm.typesafe_judge.build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_native_protocol_normalization_cache_and_report(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["Authorization"] == "Bearer test-only-key"
        body = json.loads(request.content)
        calls.append(body)
        assert set(body) == {"model", "state", "questions"}
        assert body["model"] == "jev-latest"
        assert body["state"]["segment"]["text"] == "城市发展"
        assert "UNVERIFIED_QUERY" not in request.content.decode()
        assert "image_url" not in request.content.decode()
        assert all(q["type"] == "score" and q["criteria"] == list(CRITERIA) for q in body["questions"].values())
        # Answer maps may be returned in another order; names, not positions, identify candidates.
        data = response(body)
        names = list(data["answers"])
        if len(names) > 1:
            data["answers"][names[1]] = {**answer(), "score": 1.0, "confidence": 0.3, "probabilities": {"0": 0, "1": 1, "2": 0, "3": 0, "4": 0}}
        data["answers"] = dict(reversed(list(data["answers"].items())))
        return httpx.Response(200, json=data)

    mock_client(monkeypatch, handler)
    scorer = judge(tmp_path)
    scored = asyncio.run(scorer.score_candidates(segment(), [candidate(), candidate("asset:two")]))
    assert [c.relevance_score for c in scored] == [0.8, 0.25]
    assert scored[0].quality_signals["score_method"] == "typesafe_jev_metadata"
    assert scored[0].quality_signals["judge_details"]["confidence"] == 0.91
    cached = asyncio.run(scorer.score_candidates(segment(), [candidate("asset:two"), candidate()]))
    assert len(calls) == 1
    assert [c.relevance_score for c in cached] == [0.25, 0.8]
    assert cached[1].quality_signals["judge_details"] == scored[0].quality_signals["judge_details"]

    result = MatchResult(
        created_at="2026-10-01T00:00:00+00:00", total_segments=1, analysis=AnalysisResult(segments=[segment()]),
        segments=[SegmentMatch(segment=segment(), chosen=scored[0], alternatives=[scored[1]])],
        match_summary=MatchSummary(), output_dir=str(tmp_path / "out"),
    )
    write_match_outputs(result, result.output_dir)
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["segments"][0]["chosen"]["judge_details"]["model"] == "jev-contract-test"
    assert manifest["segments"][0]["alternatives"][0]["judge_details"]["confidence"] == 0.3
    html = (tmp_path / "out" / "review.html").read_text()
    assert "模型置信度" in html and "0.91" in html and "jev-contract-test" in html


@pytest.mark.parametrize("field,value", [
    ("score", -1), ("score", 5), ("score", float("nan")), ("score", True),
    ("confidence", 1.1), ("confidence", None),
    ("type", "choice"), ("probabilities", {"0": 1}), ("legend", {}),
    ("probabilities", {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}),
    ("probabilities", {"0": 1, "1": 0, "2": 0, "3": 0, "4": 0}),
])
def test_invalid_answers_fail_without_persisting_scores(tmp_path, monkeypatch, field, value):
    def handler(request):
        data = response(json.loads(request.content))
        data["answers"]["candidate_1"][field] = value
        # Encode NaN manually because httpx deliberately refuses nonfinite json= input.
        return httpx.Response(200, content=json.dumps(data).encode())
    mock_client(monkeypatch, handler)
    scorer = judge(tmp_path)
    with pytest.raises(ValueError, match="Typesafe"):
        asyncio.run(scorer.score_candidates(segment(), [candidate()]))
    assert scorer.cache.load_json("judge", scorer._cache_key(segment(), [candidate()])) is None


def test_missing_answer_fails_and_explicit_fallback_is_not_cached(tmp_path, monkeypatch):
    mock_client(monkeypatch, lambda request: httpx.Response(200, json={"model": "jev-contract-test", "answers": {}}))
    with pytest.raises(ValueError, match="no score answer"):
        asyncio.run(judge(tmp_path).score_candidates(segment(), [candidate()]))
    scorer = judge(tmp_path, allow_fallback=True)
    previously_scored = candidate()
    previously_scored.quality_signals["judge_details"] = {"confidence": 0.9}
    result = asyncio.run(scorer.score_candidates(segment(), [previously_scored]))
    assert result[0].quality_signals["score_method"] == "heuristic"
    assert "judge_details" not in result[0].quality_signals
    assert scorer.cache.load_json("judge", scorer._cache_key(segment(), [candidate()])) is None


def test_authentication_error_is_not_retried(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={"detail": "Unauthorized"})
    mock_client(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(judge(tmp_path).score_candidates(segment(), [candidate()]))
    assert len(calls) == 1


def test_typesafe_rejects_vision_before_sending_request(tmp_path, monkeypatch):
    mock_client(monkeypatch, lambda request: pytest.fail("Vision request must not be sent"))
    with pytest.raises(ValueError, match="Vision judging"):
        asyncio.run(judge(tmp_path, allow_vision=True).score_candidates(segment(), [candidate()]))
    with pytest.raises(ValueError, match="not image input"):
        ModelSettings(provider="typesafe", supports_vision=True)


def test_provider_credentials_are_isolated_and_doctor_is_honest(tmp_path, monkeypatch):
    for name in ["JUDGE_MODEL_PROVIDER", "JUDGE_MODEL_NAME", "JUDGE_MODEL", "JUDGE_MODEL_API_KEY", "JUDGE_MODEL_BASE_URL", "JUDGE_MODEL_SUPPORTS_VISION", "TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "TYPESAFE_DEFAULT_MODEL"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "other-provider-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://other-provider.example")
    config = tmp_path / "config.toml"
    config.write_text('[judge_model]\nprovider = "typesafe"\n')
    settings = Settings.from_file(str(config))
    assert settings.judge_model.model == "jev-latest"
    assert settings.judge_model.base_url == "https://api.typesafe.ai"
    assert settings.judge_model.api_key == ""
    doctor = CliRunner().invoke(app, ["doctor", "--config", str(config)])
    assert doctor.exit_code == 0
    payload = json.loads(doctor.stdout)
    assert payload["judge_model"]["api_key_configured"] is False
    assert "other-provider-key" not in doctor.stdout
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-key")
    assert Settings.from_file(str(config)).judge_model.api_key == "test-only-key"
    monkeypatch.setenv("JUDGE_MODEL_API_KEY", "explicit-test-key")
    assert Settings.from_file(str(config)).judge_model.api_key == "explicit-test-key"
    monkeypatch.setenv("JUDGE_MODEL_SUPPORTS_VISION", "true")
    with pytest.raises(ValueError, match="not image input"):
        Settings.from_file(str(config))


def test_local_library_description_reaches_typesafe_state(tmp_path, monkeypatch):
    asset = LibraryAsset(path="/library/city.jpg", asset_type="image", title="City", description="Pedestrians crossing a city street", tags=["city"])
    local = LocalLibraryMatcher().match(segment(), [asset])[0]
    def handler(request):
        body = json.loads(request.content)
        assert body["state"]["candidates"]["candidate_1"]["description"] == asset.description
        assert "/library/" not in request.content.decode()
        return httpx.Response(200, json=response(body))
    mock_client(monkeypatch, handler)
    scored = asyncio.run(judge(tmp_path).score_candidates(segment(), [local]))[0]
    assert scored.quality_signals["judge_details"]["evidence"] == "metadata"
    assert "local_match_score" in scored.quality_signals


@pytest.mark.parametrize("raw_score,expected_chosen", [(3.2, False), (3.6, True)])
def test_full_match_pipeline_with_native_jev_and_commons(tmp_path, monkeypatch, raw_score, expected_chosen):
    from pathlib import Path
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/v1/chat/completions":
            content = json.dumps({"segments": [{"id": 1, "text": "城市发展", "visual_type": "stock_image", "scene_type": "b_roll", "search_queries": ["urban skyline"]}]})
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        if request.url.path == "/v1/systemone":
            assert request.url.host == "api.typesafe.ai"
            data = response(json.loads(request.content))
            for item in data["answers"].values():
                item["score"] = raw_score
                item["probabilities"] = {"0": 0, "1": 0, "2": 0, "3": 4 - raw_score, "4": raw_score - 3}
            return httpx.Response(200, json=data)
        assert request.url.path == "/w/api.php"
        return httpx.Response(200, json={"query": {"pages": {"5": {
            "pageid": 5, "title": "File:City skyline.jpg", "imageinfo": [{
                "url": "https://upload.wikimedia.org/city.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:City_skyline.jpg",
                "width": 1080, "height": 1920, "mime": "image/jpeg",
                "extmetadata": {"LicenseShortName": {"value": "CC0"}, "ImageDescription": {"value": "Urban architecture"}},
            }],
        }}}})
    for module in ["cmm.typesafe_judge", "cmm.analyzer.llm_analyzer", "cmm.fetcher.commons"]:
        monkeypatch.setattr(module + ".build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    settings = Settings(
        planner_model=ModelSettings(model="planner-test", api_key="planner-test-key", base_url="https://planner.example/v1"),
        judge_model=ModelSettings(provider="typesafe", api_key="test-only-key"), sources={"enabled": ["commons"]},
    )
    result = asyncio.run(match_script(
        MatchInput(text="城市发展", aspect="9:16", output_dir=str(tmp_path), save_candidates=False),
        settings, str(Path(__file__).resolve().parents[1] / "data"),
    ))
    assert set(calls) == {"/v1/chat/completions", "/v1/systemone", "/w/api.php"}
    chosen = result.segments[0].chosen
    assert (chosen is not None) == expected_chosen
    reviewed = chosen or result.segments[0].alternatives[0]
    assert reviewed.relevance_score == raw_score / 4
    assert reviewed.quality_signals["judge_details"]["model"] == "jev-contract-test"
    assert not result.warnings and not result.segments[0].fallback_used
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    item = manifest["segments"][0]
    assert (item["chosen"] or item["alternatives"][0])["judge_details"]["confidence"] == 0.91
