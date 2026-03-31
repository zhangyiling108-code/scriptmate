from pathlib import Path

from cmm.cache import FileCache
from cmm.config import MatchingSettings, SourcesSettings
from cmm.fetcher.fallback import FallbackManager
from cmm.fetcher.stock_search import StockSearchService
from cmm.models import MaterialCandidate, Segment


def test_stock_search_dedupes_and_filters_low_resolution(tmp_path: Path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}", encoding="utf-8")
    generic_dir = tmp_path / "generic"
    generic_dir.mkdir()

    service = StockSearchService(
        SourcesSettings(),
        MatchingSettings(video_min_resolution=1080, video_orientation="vertical"),
        FallbackManager(str(mapping), str(generic_dir)),
        FileCache(str(tmp_path / "cache")),
    )

    async def fake_provider_search(provider: str, query: str, segment: Segment):
        return [
            MaterialCandidate(
                id="{0}-1".format(provider),
                source_type=provider,  # type: ignore[arg-type]
                media_type="video",
                uri="https://example.com/shared.mp4",
                thumbnail_url="https://example.com/shared.jpg",
                height=1920,
                width=1080,
            ),
            MaterialCandidate(
                id="{0}-2".format(provider),
                source_type=provider,  # type: ignore[arg-type]
                media_type="video",
                uri="https://example.com/low.mp4",
                thumbnail_url="https://example.com/low.jpg",
                height=720,
                width=1280,
            ),
        ]

    service._cached_provider_search = fake_provider_search  # type: ignore[method-assign]
    segment = Segment(id=1, text="经济增长", search_queries=["economic growth"], keywords_en=["economic growth"])
    results = __import__("asyncio").run(service.search(segment))

    assert len(results) == 1
    assert results[0].uri == "https://example.com/shared.mp4"


def test_stock_search_expands_china_context_queries(tmp_path: Path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}", encoding="utf-8")
    generic_dir = tmp_path / "generic"
    generic_dir.mkdir()

    service = StockSearchService(
        SourcesSettings(),
        MatchingSettings(video_min_resolution=1080, video_orientation="vertical"),
        FallbackManager(str(mapping), str(generic_dir)),
        FileCache(str(tmp_path / "cache")),
    )

    segment = Segment(
        id=1,
        text="中国高铁和基础设施快速发展",
        search_queries=["high speed rail", "bridge infrastructure"],
        keywords_en=["china", "high speed rail", "infrastructure"],
    )

    expanded = service._expand_queries(segment.search_queries, segment)

    assert "china high speed rail" in expanded or "high speed rail china" in expanded
    assert "china infrastructure" in expanded


def test_stock_search_uses_segment_context_layers_and_subject(tmp_path: Path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}", encoding="utf-8")
    generic_dir = tmp_path / "generic"
    generic_dir.mkdir()

    service = StockSearchService(
        SourcesSettings(),
        MatchingSettings(video_min_resolution=1080, video_orientation="vertical"),
        FallbackManager(str(mapping), str(generic_dir)),
        FileCache(str(tmp_path / "cache")),
    )

    segment = Segment(
        id=1,
        text="芯片禁令与AI监管框架正在重塑美国AI竞争。",
        narrative_subject="united states artificial intelligence competition story",
        context_statement="united states artificial intelligence competition story: policy and compute competition",
        context_tags=["united states", "artificial intelligence", "competition story"],
        search_queries=["ai regulation"],
        search_query_layers={
            "l1": ["ai regulation"],
            "l2": ["chip export controls"],
            "l3": ["us ai policy"],
            "l4": ["washington technology regulation"],
            "context": ["united states artificial intelligence competition story"],
        },
        keywords_en=["united states", "artificial intelligence"],
    )

    queries = service._segment_queries(segment)

    assert "ai regulation" in queries
    assert "united states artificial intelligence competition story" in queries
    assert "united states artificial intelligence competition story real footage" in queries
    assert "us ai policy" in queries


def test_stock_search_expands_multiple_geo_modifiers_for_compare_context(tmp_path: Path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}", encoding="utf-8")
    generic_dir = tmp_path / "generic"
    generic_dir.mkdir()

    service = StockSearchService(
        SourcesSettings(),
        MatchingSettings(video_min_resolution=1080, video_orientation="vertical"),
        FallbackManager(str(mapping), str(generic_dir)),
        FileCache(str(tmp_path / "cache")),
    )

    segment = Segment(
        id=1,
        text="中美AI竞争进入生态战争阶段。",
        narrative_subject="united states artificial intelligence competition story",
        context_tags=["china", "united states", "artificial intelligence", "competition story"],
        search_queries=["ai competition"],
        keywords_en=["china", "united states", "ai", "competition"],
    )

    expanded = service._expand_queries(segment.search_queries, segment)

    assert "china ai competition" in expanded
    assert "united states ai competition" in expanded


def test_stock_search_cache_key_changes_with_orientation_and_resolution(tmp_path: Path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}", encoding="utf-8")
    generic_dir = tmp_path / "generic"
    generic_dir.mkdir()
    cache = FileCache(str(tmp_path / "cache"))
    segment = Segment(id=1, text="heart monitor", search_queries=["heart monitor"], keywords_en=["heart", "monitor"])
    calls = {"count": 0}

    async def fake_search(self, segment: Segment, query: str):
        calls["count"] += 1
        return [
            MaterialCandidate(
                id="pexels:1",
                source_type="pexels",
                media_type="video",
                uri="https://example.com/one.mp4",
                width=1080,
                height=1920,
            )
        ]

    original = __import__("cmm.fetcher.pexels", fromlist=["PexelsProvider"]).PexelsProvider.search
    __import__("cmm.fetcher.pexels", fromlist=["PexelsProvider"]).PexelsProvider.search = fake_search
    try:
        service_vertical = StockSearchService(
            SourcesSettings(enabled=["pexels"]),
            MatchingSettings(video_min_resolution=1080, video_orientation="vertical", search_pool_size=8),
            FallbackManager(str(mapping), str(generic_dir)),
            cache,
        )
        service_horizontal = StockSearchService(
            SourcesSettings(enabled=["pexels"]),
            MatchingSettings(video_min_resolution=2160, video_orientation="horizontal", search_pool_size=10),
            FallbackManager(str(mapping), str(generic_dir)),
            cache,
        )

        __import__("asyncio").run(service_vertical._cached_provider_search("pexels", "heart monitor", segment))
        __import__("asyncio").run(service_vertical._cached_provider_search("pexels", "heart monitor", segment))
        __import__("asyncio").run(service_horizontal._cached_provider_search("pexels", "heart monitor", segment))
    finally:
        __import__("cmm.fetcher.pexels", fromlist=["PexelsProvider"]).PexelsProvider.search = original

    assert calls["count"] == 2
