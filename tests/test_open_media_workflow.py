import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
from PIL import Image
from typer.testing import CliRunner

from cmm.cache import FileCache
from cmm.cli import app
from cmm.config import MatchingSettings, ModelSettings, OpenSourceSettings, Settings, SourcesSettings
from cmm.fetcher.commons import CommonsProvider
from cmm.fetcher.fallback import FallbackManager
from cmm.fetcher.openverse import OpenverseProvider
from cmm.fetcher.pexels import PexelsProvider
from cmm.fetcher.pixabay import PixabayProvider
from cmm.fetcher.stock_search import StockSearchService
from cmm.library.matcher import LocalLibraryMatcher
from cmm.library.scanner import scan_library
from cmm.models import AnalysisResult, MaterialCandidate, MatchResult, MatchSummary, Segment, SegmentMatch
from cmm.outputs.writer import write_match_outputs
from cmm.scorer import SemanticScorer
from cmm.utils.retry import with_retry


def image_candidate(identifier="one", **kwargs):
    return MaterialCandidate(id=identifier, source_type="commons", media_type="image", uri="https://example.org/" + identifier + ".jpg", width=1080, height=1920, **kwargs)


def service(tmp_path, enabled, **matching):
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}")
    return StockSearchService(SourcesSettings(enabled=enabled), MatchingSettings(**matching), FallbackManager(str(mapping), str(tmp_path)), FileCache(str(tmp_path / "cache")))


def scorer(tmp_path, **kwargs):
    settings = ModelSettings(provider="compatible", model="vision-model", api_key="test", base_url="https://example.org/v1", supports_vision=True)
    return SemanticScorer(settings, FileCache(str(tmp_path / "judge")), **kwargs)


def mock_client(monkeypatch, module, handler):
    monkeypatch.setattr(module + ".build_async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_pexels_image_request_uses_photo_api_and_real_description(monkeypatch):
    def handler(request):
        assert request.url.path == "/v1/search"
        assert request.headers["Authorization"] == "test"
        return httpx.Response(200, json={"photos": [{"id": 7, "width": 1080, "height": 1920, "alt": "A Shanghai tower", "photographer": "Alice", "url": "https://pexels.com/photo/7/", "src": {"original": "https://example.org/full.jpg", "medium": "https://example.org/thumb.jpg"}}]})
    mock_client(monkeypatch, "cmm.fetcher.pexels", handler)
    result = asyncio.run(PexelsProvider("test", MatchingSettings()).search(Segment(id=1, text="城市", visual_type="stock_image"), "city"))
    assert result[0].media_type == "image"
    assert result[0].provider_meta["title"] == "A Shanghai tower"
    assert result[0].creator == "Alice"
    assert "city" not in result[0].tags


def test_pixabay_stock_image_does_not_request_videos(monkeypatch):
    def handler(request):
        assert request.url.path == "/api/"
        return httpx.Response(200, json={"hits": [{"id": 1, "largeImageURL": "https://example.org/image.jpg", "tags": "city, tower", "user": "Alice", "imageWidth": 1080, "imageHeight": 1920}]})
    mock_client(monkeypatch, "cmm.fetcher.pixabay", handler)
    result = asyncio.run(PixabayProvider("test", MatchingSettings()).search(Segment(id=1, text="城市", visual_type="stock_image"), "unverified query"))
    assert result[0].tags == ["city", "tower"]


def test_openverse_search_preserves_license_and_excludes_nc(monkeypatch):
    def handler(request):
        assert request.url.path == "/v1/images/"
        assert request.url.params["q"] == "上海"
        assert request.url.params["license"] == "cc0,pdm,by"
        assert request.headers["Authorization"] == "Bearer optional-token"
        return httpx.Response(200, json={"results": [
            {"id": "good", "url": "https://example.org/a.jpg", "foreign_landing_url": "https://example.org/source", "license": "by", "license_version": "4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "creator": "Alice", "title": "上海", "width": 1080, "height": 1920},
            {"id": "nc", "url": "https://example.org/b.jpg", "license": "by-nc"},
        ]})
    mock_client(monkeypatch, "cmm.fetcher.openverse", handler)
    provider = OpenverseProvider(OpenSourceSettings(base_url="https://api.openverse.org/v1", api_key="optional-token"), MatchingSettings())
    candidates = asyncio.run(provider.search(Segment(id=1, text="上海", visual_type="stock_image"), "上海"))
    assert len(candidates) == 1
    assert candidates[0].license_type == "by"
    assert candidates[0].license_version == "4.0"
    assert candidates[0].attribution_required
    assert "Alice" in candidates[0].attribution


def commons_page(code="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/"):
    return {"pageid": 5, "title": "File:Shanghai.jpg", "imageinfo": [{"url": "https://upload.wikimedia.org/Shanghai.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Shanghai.jpg", "width": 1080, "height": 1920, "mime": "image/jpeg", "extmetadata": {"LicenseShortName": {"value": code}, "LicenseUrl": {"value": license_url}, "Artist": {"value": '<a href="https://example.org/alice">Alice</a>'}, "ObjectName": {"value": "上海"}}}]}


def test_commons_gets_imageinfo_and_normalizes_author(monkeypatch):
    def handler(request):
        assert request.url.params["gsrnamespace"] == "6"
        assert "extmetadata" in request.url.params["iiprop"]
        return httpx.Response(200, json={"query": {"pages": {"5": commons_page()}}})
    mock_client(monkeypatch, "cmm.fetcher.commons", handler)
    provider = CommonsProvider(OpenSourceSettings(base_url="https://commons.wikimedia.org/w/api.php"), MatchingSettings())
    candidate = asyncio.run(provider.search(Segment(id=1, text="上海", visual_type="stock_image"), "上海"))[0]
    assert candidate.creator == "Alice"
    assert candidate.license_type == "by"
    assert candidate.attribution_required
    assert provider._candidate(commons_page("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"), "上海") is None
    assert provider._candidate(commons_page("unknown", ""), "上海") is None


def test_commons_api_error_is_not_an_empty_success(monkeypatch):
    mock_client(monkeypatch, "cmm.fetcher.commons", lambda request: httpx.Response(200, json={"error": {"code": "badvalue"}}))
    provider = CommonsProvider(OpenSourceSettings(base_url="https://commons.wikimedia.org/w/api.php"), MatchingSettings())
    with pytest.raises(ValueError, match="rejected"):
        asyncio.run(provider.search(Segment(id=1, text="city", visual_type="stock_image"), "city"))


def test_new_sources_use_chinese_queries_only_for_images(tmp_path):
    search = service(tmp_path, ["openverse", "commons", "coverr"])
    calls = []
    async def fake(provider, query, segment):
        calls.append((provider, query))
        return [image_candidate()]
    search._cached_provider_search = fake
    result = asyncio.run(search.search(Segment(id=1, text="上海", visual_type="stock_image", search_queries=["上海", "Shanghai"])))
    assert result
    assert ("commons", "上海") in calls
    assert ("openverse", "上海") in calls
    assert all(provider != "coverr" for provider, _ in calls)
    calls.clear()
    assert asyncio.run(search.search(Segment(id=1, text="上海", search_queries=["Shanghai"])))
    assert all(provider == "coverr" for provider, _ in calls)


def test_cross_source_deduplication_uses_original_page(tmp_path):
    search = service(tmp_path, ["commons"])
    a = image_candidate("a", source_page="https://commons.wikimedia.org/wiki/File:Shanghai.jpg")
    b = image_candidate("b", source_page="http://commons.wikimedia.org/wiki/File:Shanghai.jpg")
    b.source_type = "openverse"
    assert len(search._dedupe([a, b])) == 1


def test_provider_failure_is_visible_and_credentials_are_redacted(tmp_path):
    search = service(tmp_path, ["commons", "openverse"])
    async def fake(provider, query, segment):
        if provider == "commons":
            request = httpx.Request("GET", "https://example.org/?key=secret")
            raise httpx.HTTPStatusError("secret", request=request, response=httpx.Response(403, request=request))
        return [image_candidate()]
    search._cached_provider_search = fake
    result = asyncio.run(search.search_query("city", media_type="image"))
    assert result.candidates
    assert result.warnings == ["commons: search failed (HTTP 403)"]
    assert "secret" not in json.dumps(result.model_dump())


def test_search_has_global_and_provider_concurrency_limits(tmp_path):
    search = service(tmp_path, ["commons"], search_concurrency=3, provider_concurrency=2)
    active = peak = 0
    async def fake(provider, query, segment):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return []
    search._cached_provider_search = fake
    asyncio.run(search._search_queries(["city" + str(i) for i in range(8)], Segment(id=1, text="city", visual_type="stock_image")))
    assert peak == 2


def test_search_timeout_is_reported(tmp_path):
    search = service(tmp_path, ["commons"], search_timeout_seconds=0.01)
    async def fake(provider, query, segment):
        await asyncio.Event().wait()
    search._cached_provider_search = fake
    result = asyncio.run(search.search_query("city", media_type="image"))
    assert not result.candidates
    assert result.warnings == ["commons: search failed (request timed out)"]


def test_judge_cache_reuses_scores_when_candidate_batch_changes(tmp_path, monkeypatch):
    judge = scorer(tmp_path)
    calls = []
    async def fake(segment, candidates):
        calls.append([candidate.id for candidate in candidates])
        return [{"id": candidate.id, "score": 0.72, "reason": "match"} for candidate in candidates]
    monkeypatch.setattr(judge, "_request_scores", fake)
    segment = Segment(id=1, text="city")
    asyncio.run(judge.score_candidates(segment, [image_candidate("a"), image_candidate("b")]))
    result = asyncio.run(judge.score_candidates(segment, [image_candidate("b"), image_candidate("c")]))
    assert calls == [["a", "b"], ["c"]]
    assert [candidate.id for candidate in result] == ["b", "c"]


def test_judge_cache_separates_vision_and_editorial_context(tmp_path):
    judge = scorer(tmp_path)
    vision_judge = scorer(tmp_path, allow_vision=True)
    segment = Segment(id=1, text="city", narrative_subject="china")
    candidate = image_candidate()
    assert judge._cache_key(segment, [candidate]) != vision_judge._cache_key(segment, [candidate])
    assert judge._cache_key(segment, [candidate]) != judge._cache_key(segment.model_copy(update={"narrative_subject": "japan"}), [candidate])


def test_explicit_model_capability_is_honored(tmp_path):
    judge = scorer(tmp_path, allow_vision=True)
    judge.settings.provider = "deepseek"
    assert judge._supports_image_input()
    judge.settings.supports_vision = False
    with pytest.raises(ValueError, match="supports_vision"):
        asyncio.run(judge.score_candidates(Segment(id=1, text="city"), [image_candidate()]))


def test_vision_request_encodes_local_image(monkeypatch, tmp_path):
    image = tmp_path / "city.png"
    Image.new("RGB", (1800, 2400), "navy").save(image)
    def handler(request):
        payload = json.loads(request.content)
        content = payload["messages"][1]["content"]
        evidence = [part for part in content if part["type"] == "image_url"]
        assert evidence[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"scores":[{"id":"local","score":0.8,"reason":"Visible skyline"}]}'}}]})
    mock_client(monkeypatch, "cmm.scorer", handler)
    candidate = MaterialCandidate(id="local", source_type="local", media_type="image", uri=str(image), thumbnail_url=str(image))
    result = asyncio.run(scorer(tmp_path, allow_vision=True).score_candidates(Segment(id=1, text="city"), [candidate]))
    assert result[0].relevance_score == 0.8


def test_judge_does_not_cache_transient_fallback(tmp_path, monkeypatch):
    judge = scorer(tmp_path, allow_fallback=True)
    calls = []
    async def fake(segment, candidates):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporarily down")
        return [{"id": candidate.id, "score": 0.8, "reason": "Recovered"} for candidate in candidates]
    monkeypatch.setattr(judge, "_request_scores", fake)
    segment = Segment(id=1, text="city")
    asyncio.run(judge.score_candidates(segment, [image_candidate()]))
    result = asyncio.run(judge.score_candidates(segment, [image_candidate()]))
    assert len(calls) == 2
    assert result[0].reason == "Recovered"


def test_invalid_judge_score_fails_without_silent_downgrade(tmp_path, monkeypatch):
    judge = scorer(tmp_path)
    async def fake(segment, candidates):
        return [{"id": candidates[0].id, "score": float("nan"), "reason": "invalid"}]
    monkeypatch.setattr(judge, "_request_scores", fake)
    with pytest.raises(ValueError, match="finite"):
        asyncio.run(judge.score_candidates(Segment(id=1, text="city"), [image_candidate()]))


def test_cache_expiry_corruption_and_atomic_replacement(tmp_path):
    cache = FileCache(str(tmp_path))
    path = cache.save_json("search", "query", {"ok": True})
    os.utime(path, (1, 1))
    assert cache.load_json("search", "query", max_age_seconds=60) is None
    path.write_text('{"partial":')
    assert cache.load_json("search", "query") is None
    cache.save_json("search", "query", {"ok": True})
    with pytest.raises(TypeError):
        cache.save_json("search", "query", {"not-json": object()})
    assert cache.load_json("search", "query") == {"ok": True}
    assert list(path.parent.iterdir()) == [path]


def test_retry_does_not_repeat_auth_denials(monkeypatch):
    calls = []
    async def denied():
        calls.append(1)
        request = httpx.Request("GET", "https://example.org")
        raise httpx.HTTPStatusError("denied", request=request, response=httpx.Response(403, request=request))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(with_retry(denied))
    assert len(calls) == 1


def test_retry_honors_rate_limit_delay(monkeypatch):
    delays = []
    async def no_wait(delay):
        delays.append(delay)
    monkeypatch.setattr("cmm.utils.retry.asyncio.sleep", no_wait)
    calls = []
    async def request():
        calls.append(1)
        if len(calls) == 1:
            req = httpx.Request("GET", "https://example.org")
            raise httpx.HTTPStatusError("quota", request=req, response=httpx.Response(429, headers={"Retry-After": "2"}, request=req))
        return "ok"
    assert asyncio.run(with_retry(request)) == "ok"
    assert delays == [2]


def test_local_library_preserves_imported_license(tmp_path):
    Image.new("RGB", (1080, 1920)).save(tmp_path / "city.jpg")
    metadata = tmp_path / "metadata.jsonl"
    metadata.write_text(json.dumps({"path": "city.jpg", "title": "city", "tags": ["city"], "license_type": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/", "creator": "Alice", "attribution_required": True, "source_page": "https://example.org/city"}))
    scan = scan_library(str(tmp_path), str(metadata))
    result = LocalLibraryMatcher().match(Segment(id=1, text="city", keywords_en=["city"]), scan.assets)
    assert result[0].license_type == "by"
    assert result[0].creator == "Alice"
    assert result[0].attribution_required
    assert result[0].source_page == "https://example.org/city"


def test_license_and_source_failures_are_visible_in_review_outputs(tmp_path):
    segment = Segment(id=1, text="city")
    candidate = image_candidate(creator="Alice <script>", license_type="by", license_url="https://creativecommons.org/licenses/by/4.0/", attribution_required=True, attribution="Alice · CC BY 4.0")
    result = MatchResult(created_at="now", total_segments=1, analysis=AnalysisResult(segments=[segment]), segments=[SegmentMatch(segment=segment, chosen=candidate)], match_summary=MatchSummary(), output_dir=str(tmp_path), warnings=["commons: HTTP 403"])
    write_match_outputs(result, str(tmp_path))
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["segments"][0]["chosen"]["license_url"] == candidate.license_url
    assert manifest["warnings"] == ["commons: HTTP 403"]
    review = (tmp_path / "review.html").read_text()
    assert "Alice &lt;script&gt;" in review
    assert "commons: HTTP 403" in review
    assert "CC BY 4.0" in (tmp_path / "attributions.md").read_text()


def test_config_and_cli_expose_image_sources(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('[sources]\nenabled=["commons", "openverse"]\n[sources.commons]\nallowed_licenses=["cc0"]\n[judge_model]\nsupports_vision=true\n')
    settings = Settings.from_file(str(path))
    assert settings.sources.commons.allowed_licenses == ["cc0"]
    assert settings.judge_model.supports_vision is True
    captured = {}
    async def fake(query, settings, cache, data_dir, **kwargs):
        captured.update(kwargs)
        from cmm.models import SearchResult
        return SearchResult(query=query, source=kwargs["source"])
    monkeypatch.setattr("cmm.cli.search_single_query", fake)
    result = CliRunner().invoke(app, ["search", "上海", "--source", "commons", "--media-type", "image", "--aspect", "9:16", "--config", str(path), "-o", str(tmp_path / "output")])
    assert result.exit_code == 0
    assert captured["media_type"] == "image"
    invalid = CliRunner().invoke(app, ["search", "city", "--media-type", "audio", "--aspect", "9:16"])
    assert invalid.exit_code != 0


def test_full_match_uses_open_media_and_emits_licensed_package(tmp_path, monkeypatch):
    from cmm.models import MatchInput
    from cmm.pipeline import match_script
    import re

    def handler(request):
        if request.url.path.endswith("chat/completions"):
            payload = json.loads(request.content)
            if payload["model"] == "planner":
                content = json.dumps({"segments": [{"id": 1, "text": "上海城市建筑", "visual_type": "stock_image", "scene_type": "b_roll", "search_queries": ["Shanghai city"], "keywords_cn": ["上海"]}], "overall_style": "documentary"})
            else:
                text = " ".join(part.get("text", "") for part in payload["messages"][1]["content"])
                identifiers = re.findall(r"Candidate \d+: id=([^,]+),", text)
                assert identifiers
                content = json.dumps({"scores": [{"id": identifier, "score": 0.9, "reason": "City architecture"} for identifier in identifiers]})
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        assert request.url.path == "/w/api.php"
        pages = {}
        for identifier in range(3):
            page = commons_page()
            page["pageid"] = identifier
            page["title"] = "File:City" + str(identifier) + ".jpg"
            info = page["imageinfo"][0]
            info["url"] = "https://upload.wikimedia.org/City" + str(identifier) + ".jpg"
            info["descriptionurl"] = "https://commons.wikimedia.org/wiki/" + page["title"]
            pages[str(identifier)] = page
        return httpx.Response(200, json={"query": {"pages": pages}})

    for module in ["cmm.analyzer.llm_analyzer", "cmm.scorer", "cmm.fetcher.commons"]:
        mock_client(monkeypatch, module, handler)
    settings = Settings(sources=SourcesSettings(enabled=["commons"]), planner_model=ModelSettings(model="planner", api_key="test", base_url="https://model.example.org/v1"), judge_model=ModelSettings(model="judge", api_key="test", base_url="https://model.example.org/v1"))
    result = asyncio.run(match_script(MatchInput(text="上海城市建筑", aspect="9:16", output_dir=str(tmp_path), save_candidates=False), settings, str(Path(__file__).resolve().parents[1] / "data")))
    assert result.segments[0].chosen.source_type == "commons"
    assert len(result.segments[0].alternatives) == 2
    assert result.segments[0].chosen.attribution_required
    assert not result.warnings
    assert not result.segments[0].fallback_used
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["segments"][0]["chosen"]["creator"] == "Alice"
    assert all((tmp_path / name).exists() for name in ["analysis.json", "manifest.json", "summary.md", "review.html", "segments_overview.csv", "attributions.md"])
