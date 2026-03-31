import json
from pathlib import Path

from cmm.config import ExternalSourceSettings, Settings
from cmm.models import MatchInput, MaterialCandidate, Segment, SegmentMatch
from cmm.pipeline import _action_for_segment, _build_summary, match_script


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_match_script_writes_manifest_and_segment_outputs(tmp_path: Path, monkeypatch):
    data_dir = DATA_DIR
    settings = Settings()
    settings.planner_model.provider = "openai"
    settings.planner_model.model = "gpt-4.1-mini"
    settings.planner_model.base_url = "https://example.com/v1"
    settings.planner_model.api_key = "x"
    settings.judge_model.provider = "openai"
    settings.judge_model.model = "gpt-4o-mini"
    settings.judge_model.base_url = "https://example.com/v1"
    settings.judge_model.api_key = "x"
    settings.sources.pexels.api_key = "demo"
    settings.sources.pixabay.api_key = "demo"
    settings.sources.extra = [
        ExternalSourceSettings(
            name="vjshi",
            enabled=True,
            kind="manual",
            license="freemium",
            priority=20,
            home_url="https://www.vjshi.com/",
            search_url_template="https://www.vjshi.com/search?wd={query}",
            notes="Domestic footage library",
        )
    ]

    async def fake_request_completion(self, prompt: str):
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "大家好，今天聊经济增长",
              "segment_role": "hook",
              "visual_type": "skip",
              "scene_type": "talking_head",
              "search_queries": ["economic growth"],
              "search_query_layers": {"l1": ["economic growth"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["经济增长"],
              "keywords_en": ["economic growth"],
              "card_text": "",
              "visual_brief": "clean visual"
            },
            {
              "id": 2,
              "text": "近年来我国GDP持续增长",
              "segment_role": "claim",
              "visual_type": "stock_video",
              "scene_type": "b_roll",
              "search_queries": ["economic growth"],
              "search_query_layers": {"l1": ["economic growth"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["经济增长"],
              "keywords_en": ["economic growth"],
              "card_text": "",
              "visual_brief": "city prosperity"
            },
            {
              "id": 3,
              "text": "最后总结一下核心观点",
              "segment_role": "summary",
              "visual_type": "text_card",
              "scene_type": "text_card",
              "search_queries": ["summary"],
              "search_query_layers": {"l1": ["summary"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["总结"],
              "keywords_en": ["summary"],
              "card_text": "最后总结一下核心观点",
              "visual_brief": "card"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    async def fake_request_scores(self, segment, candidates, batch_size=4):
        return [{"id": candidate.id, "score": 0.91, "reason": "High match."} for candidate in candidates]

    monkeypatch.setattr("cmm.analyzer.llm_analyzer.LLMAnalyzer._request_completion", fake_request_completion)
    monkeypatch.setattr("cmm.scorer.SemanticScorer._request_scores", fake_request_scores)

    async def fake_pexels_search(self, segment: Segment, query: str):
        return [
            MaterialCandidate(
                id="pexels:1",
                source_type="pexels",
                media_type="video",
                uri="https://example.com/vertical.mp4",
                thumbnail_url="https://example.com/thumb.jpg",
                preview_uri="https://example.com/thumb.jpg",
                width=1080,
                height=1920,
                provider_meta={"query": query, "title": "Vertical city"},
                quality_signals={"duration_fit": 0.85},
            )
        ]

    async def fake_pixabay_search(self, segment: Segment, query: str):
        return []

    monkeypatch.setattr("cmm.fetcher.pexels.PexelsProvider.search", fake_pexels_search)
    monkeypatch.setattr("cmm.fetcher.pixabay.PixabayProvider.search", fake_pixabay_search)

    result = __import__("asyncio").run(
        match_script(
            MatchInput(
                text="大家好，今天聊经济增长。近年来我国GDP持续增长。最后总结一下核心观点。",
                output_dir=str(tmp_path / "output"),
                save_candidates=False,
            ),
            settings=settings,
            data_dir=str(data_dir),
        )
    )

    assert result.total_segments == 3
    assert (tmp_path / "output" / "manifest.json").exists()
    assert (tmp_path / "output" / "summary.md").exists()
    assert (tmp_path / "output" / "segments_overview.csv").exists()
    assert (tmp_path / "output" / "segments" / "001" / "segment.json").exists()
    assert result.segments[0].action == "skip"
    assert result.segments[1].chosen is not None
    assert result.segments[2].chosen is not None
    manifest = json.loads((tmp_path / "output" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["segments"][0]["strategy"].startswith("策略：")
    assert manifest["segments"][1]["segment_role"] == "claim"
    assert manifest["segments"][2]["scene_type"] == "text_card"
    assert manifest["segments"][1]["recommended_duration"] == 3.0
    assert manifest["segments"][0]["asset_class"] == "host_placeholder"
    assert manifest["segments"][0]["rhythm_tag"] == "intro_hold"
    assert manifest["segments"][0]["use_status"] == "host_only"
    assert manifest["segments"][0]["confidence_band"] == "manual"
    assert manifest["segments"][0]["review_priority"] == "none"
    assert manifest["segments"][0]["review_rank"] == 0
    assert manifest["segments"][1]["asset_class"] == "broll_video"
    assert manifest["segments"][1]["rhythm_tag"] == "motion_cutaway"
    assert manifest["segments"][1]["use_status"] == "ready"
    assert manifest["segments"][1]["confidence_band"] == "high"
    assert manifest["segments"][1]["review_priority"] == "none"
    assert manifest["segments"][1]["review_rank"] == 0
    assert manifest["segments"][1]["chosen"]["source_label"] == "pexels.video"
    assert manifest["segments"][1]["external_search_links"][0]["name"] == "vjshi"
    assert "vjshi.com/search" in manifest["segments"][1]["external_search_links"][0]["url"]
    assert manifest["segments"][1]["chosen"]["selection_tag"] == "primary"
    assert manifest["segments"][1]["chosen"]["duration_fit"] == 0.85
    assert manifest["segments"][1]["chosen"]["resolution"] == "1080x1920"
    assert manifest["segments"][1]["chosen"]["orientation"] == "vertical"
    assert manifest["segments"][1]["chosen"]["quality_tier"] == "ready_vertical"
    assert manifest["segments"][1]["chosen"]["crop_risk"] == "low"
    assert manifest["segments"][2]["asset_class"] == "summary_card"
    assert manifest["segments"][2]["rhythm_tag"] == "summary_pause"
    assert manifest["segments"][2]["use_status"] == "ready"
    assert manifest["segments"][2]["confidence_band"] == "high"
    assert manifest["segments"][2]["review_priority"] == "none"
    assert manifest["segments"][2]["review_rank"] == 0
    assert manifest["segments"][2]["edit_suggestion"].startswith("作为总结卡停留 2-3 秒")
    overview = (tmp_path / "output" / "segments_overview.csv").read_text(encoding="utf-8")
    assert "segment_role,text,narrative_subject,context_statement,context_tags,visual_type,scene_type,asset_class,rhythm_tag,use_status,confidence_band,review_priority,review_rank,recommended_duration,duration_fit,resolution,orientation,quality_tier,crop_risk,source_label,direct_url,source_page,external_search_links,selection_tag,score" in overview
    assert "1,hook,大家好，今天聊经济增长" in overview
    assert "2,claim,近年来我国GDP持续增长" in overview
    assert "https://example.com/vertical.mp4" in overview
    assert "vjshi.com/search" in overview


def test_action_for_segment_distinguishes_selected_link_and_downloaded():
    segment = Segment(id=1, text="城市画面", visual_type="stock_video", scene_type="b_roll")
    remote = MaterialCandidate(id="pexels:1", source_type="pexels", media_type="video", uri="https://example.com/a.mp4")
    downloaded = remote.model_copy(update={"provider_meta": {"downloaded_path": "/tmp/a.mp4"}})
    generated = MaterialCandidate(id="data:1", source_type="data_card", media_type="image", uri="/tmp/chart.png")

    assert _action_for_segment(segment, remote) == "selected_link"
    assert _action_for_segment(segment, downloaded) == "downloaded"
    assert _action_for_segment(segment, generated) == "generated"


def test_build_summary_separates_generic_real_from_generated():
    summary = _build_summary(
        [
            SegmentMatch(
                segment=Segment(id=1, text="a", visual_type="stock_video", scene_type="b_roll"),
                chosen=MaterialCandidate(id="a", source_type="pexels", media_type="video", uri="https://e", match_level="exact"),
            ),
            SegmentMatch(
                segment=Segment(id=2, text="b", visual_type="stock_video", scene_type="b_roll"),
                chosen=MaterialCandidate(id="b", source_type="pixabay", media_type="video", uri="https://e2", match_level="generic"),
            ),
            SegmentMatch(
                segment=Segment(id=3, text="c", visual_type="data_card", scene_type="infographic"),
                chosen=MaterialCandidate(id="c", source_type="data_card", media_type="image", uri="/tmp/chart.png"),
            ),
        ]
    )

    assert summary.exact == 1
    assert summary.generic_real == 1
    assert summary.generated == 1


def test_match_script_raises_when_judge_fails_and_fallback_is_disabled(tmp_path: Path, monkeypatch):
    data_dir = DATA_DIR
    settings = Settings()
    settings.planner_model.provider = "openai"
    settings.planner_model.model = "gpt-4.1-mini"
    settings.planner_model.base_url = "https://example.com/v1"
    settings.planner_model.api_key = "x"
    settings.judge_model.provider = "openai"
    settings.judge_model.model = "gpt-4o-mini"
    settings.judge_model.base_url = "https://example.com/v1"
    settings.judge_model.api_key = "x"
    settings.sources.pexels.api_key = "demo"
    settings.sources.pixabay.api_key = "demo"

    async def fake_request_completion(self, prompt: str):
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "城市天际线、高楼与繁忙车流，展现现代经济活力",
              "segment_role": "claim",
              "visual_type": "stock_video",
              "scene_type": "b_roll",
              "search_queries": ["economic growth skyline"],
              "search_query_layers": {"l1": ["economic growth skyline"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["经济增长"],
              "keywords_en": ["economic growth skyline"],
              "card_text": "",
              "visual_brief": "city prosperity"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    async def fake_pexels_search(self, segment: Segment, query: str):
        return [
            MaterialCandidate(
                id="pexels:1",
                source_type="pexels",
                media_type="video",
                uri="https://example.com/vertical.mp4",
                thumbnail_url="https://example.com/thumb.jpg",
                preview_uri="https://example.com/thumb.jpg",
                width=1080,
                height=1920,
                provider_meta={"query": query, "title": "Vertical city"},
            )
        ]

    async def fake_pixabay_search(self, segment: Segment, query: str):
        return []

    async def fake_judge_scores(self, segment, candidates):
        raise RuntimeError("judge unavailable")

    monkeypatch.setattr("cmm.analyzer.llm_analyzer.LLMAnalyzer._request_completion", fake_request_completion)
    monkeypatch.setattr("cmm.fetcher.pexels.PexelsProvider.search", fake_pexels_search)
    monkeypatch.setattr("cmm.fetcher.pixabay.PixabayProvider.search", fake_pixabay_search)
    monkeypatch.setattr("cmm.scorer.SemanticScorer._request_scores", fake_judge_scores)

    try:
        __import__("asyncio").run(
            match_script(
                MatchInput(
                    text="城市天际线、高楼与繁忙车流，展现现代经济活力。",
                    output_dir=str(tmp_path / "output"),
                    save_candidates=False,
                ),
                settings=settings,
                data_dir=str(data_dir),
            )
        )
    except RuntimeError as exc:
        assert "judge unavailable" in str(exc)
    else:
        raise AssertionError("Expected judge failure to raise when fallback is disabled.")


def test_match_script_uses_contextual_real_search_to_fill_three_candidates(tmp_path: Path, monkeypatch):
    data_dir = DATA_DIR
    settings = Settings()
    settings.planner_model.provider = "openai"
    settings.planner_model.model = "gpt-4.1-mini"
    settings.planner_model.base_url = "https://example.com/v1"
    settings.planner_model.api_key = "x"
    settings.judge_model.provider = "openai"
    settings.judge_model.model = "gpt-4o-mini"
    settings.judge_model.base_url = "https://example.com/v1"
    settings.judge_model.api_key = "x"
    settings.sources.pexels.api_key = "demo"
    settings.sources.pixabay.api_key = "demo"

    async def fake_request_completion(self, prompt: str):
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "高铁里程从零到四万公里。",
              "segment_role": "data_point",
              "visual_type": "stock_video",
              "scene_type": "b_roll",
              "search_queries": ["high speed rail"],
              "search_query_layers": {"l1": ["high speed rail"], "l2": ["rail infrastructure"], "l3": ["china rail development"], "l4": ["china transportation growth"]},
              "keywords_cn": ["高铁"],
              "keywords_en": ["high speed rail"],
              "card_text": "",
              "visual_brief": "china rail growth"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    async def fake_request_scores(self, segment, candidates, batch_size=4):
        payload = []
        for idx, candidate in enumerate(candidates, start=1):
            payload.append({"id": candidate.id, "score": 0.88 - (idx * 0.03), "reason": "Contextual match."})
        return payload

    async def fake_pexels_search(self, segment: Segment, query: str):
        token = query.replace(" ", "-")
        return [
            MaterialCandidate(
                id=f"pexels:{token}",
                source_type="pexels",
                media_type="video",
                uri=f"https://example.com/{token}.mp4",
                thumbnail_url="https://example.com/thumb.jpg",
                preview_uri="https://example.com/thumb.jpg",
                width=1080,
                height=1920,
                provider_meta={"query": query, "title": token},
                quality_signals={"duration_fit": 0.8},
            )
        ]

    async def fake_pixabay_search(self, segment: Segment, query: str):
        return []

    monkeypatch.setattr("cmm.analyzer.llm_analyzer.LLMAnalyzer._request_completion", fake_request_completion)
    monkeypatch.setattr("cmm.scorer.SemanticScorer._request_scores", fake_request_scores)
    monkeypatch.setattr("cmm.fetcher.pexels.PexelsProvider.search", fake_pexels_search)
    monkeypatch.setattr("cmm.fetcher.pixabay.PixabayProvider.search", fake_pixabay_search)

    result = __import__("asyncio").run(
        match_script(
            MatchInput(
                text="中国经济发展二十年。高铁里程从零到四万公里。",
                output_dir=str(tmp_path / "output"),
                save_candidates=False,
            ),
            settings=settings,
            data_dir=str(data_dir),
        )
    )

    segment = result.segments[0]
    total_candidates = (1 if segment.chosen else 0) + len(segment.alternatives)
    assert total_candidates >= 3


def test_infographic_segment_does_not_auto_generate_when_generated_fallback_is_disabled(tmp_path: Path, monkeypatch):
    data_dir = DATA_DIR
    settings = Settings()
    settings.planner_model.provider = "openai"
    settings.planner_model.model = "gpt-4.1-mini"
    settings.planner_model.base_url = "https://example.com/v1"
    settings.planner_model.api_key = "x"
    settings.judge_model.provider = "openai"
    settings.judge_model.model = "gpt-4o-mini"
    settings.judge_model.base_url = "https://example.com/v1"
    settings.judge_model.api_key = "x"
    settings.sources.pexels.api_key = "demo"
    settings.sources.pixabay.api_key = "demo"

    async def fake_request_completion(self, prompt: str):
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "植物会影响身体代谢",
              "segment_role": "explanation",
              "visual_type": "stock_image",
              "scene_type": "infographic",
              "search_queries": ["plants metabolism"],
              "search_query_layers": {"l1": ["plants metabolism"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["植物", "代谢"],
              "keywords_en": ["plants", "metabolism"],
              "card_text": "",
              "visual_brief": "illustration of plants affecting metabolism"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    async def fake_pexels_search(self, segment: Segment, query: str):
        return [
            MaterialCandidate(
                id="pexels:weak",
                source_type="pexels",
                media_type="image",
                uri="https://example.com/weak.jpg",
                thumbnail_url="https://example.com/thumb.jpg",
                preview_uri="https://example.com/thumb.jpg",
                width=1080,
                height=1920,
                relevance_score=0.75,
            )
        ]

    async def fake_pixabay_search(self, segment: Segment, query: str):
        return []

    async def fake_judge_scores(self, segment, candidates):
        return [{"id": candidate.id, "score": 0.78, "reason": "Somewhat related."} for candidate in candidates]

    monkeypatch.setattr("cmm.analyzer.llm_analyzer.LLMAnalyzer._request_completion", fake_request_completion)
    monkeypatch.setattr("cmm.fetcher.pexels.PexelsProvider.search", fake_pexels_search)
    monkeypatch.setattr("cmm.fetcher.pixabay.PixabayProvider.search", fake_pixabay_search)
    monkeypatch.setattr("cmm.scorer.SemanticScorer._request_scores", fake_judge_scores)

    result = __import__("asyncio").run(
        match_script(
            MatchInput(
                text="植物会影响身体代谢。",
                output_dir=str(tmp_path / "output"),
                save_candidates=False,
            ),
            settings=settings,
            data_dir=str(data_dir),
        )
    )

    assert result.segments[0].chosen is None
    assert len(result.segments[0].alternatives) >= 1
    assert result.segments[0].notes[0].startswith("策略：")
    assert any("默认不降级" in note or "真实素材候选供人工选择" in note for note in result.segments[0].notes[1:])
    manifest = json.loads((tmp_path / "output" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["segments"][0]["asset_class"] == "unmatched"
    assert manifest["segments"][0]["rhythm_tag"] == "manual_review"
    assert manifest["segments"][0]["use_status"] == "review"
    assert manifest["segments"][0]["confidence_band"] == "low"
    assert manifest["segments"][0]["review_priority"] == "critical"
    assert manifest["segments"][0]["chosen"] is None


def test_infographic_segment_generates_card_when_generated_fallback_is_enabled(tmp_path: Path, monkeypatch):
    data_dir = DATA_DIR
    settings = Settings()
    settings.planner_model.provider = "openai"
    settings.planner_model.model = "gpt-4.1-mini"
    settings.planner_model.base_url = "https://example.com/v1"
    settings.planner_model.api_key = "x"
    settings.judge_model.provider = "openai"
    settings.judge_model.model = "gpt-4o-mini"
    settings.judge_model.base_url = "https://example.com/v1"
    settings.judge_model.api_key = "x"
    settings.sources.pexels.api_key = "demo"
    settings.sources.pixabay.api_key = "demo"
    settings.downgrade.generated_fallback = True

    async def fake_request_completion(self, prompt: str):
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "植物会影响身体代谢",
              "segment_role": "explanation",
              "visual_type": "stock_image",
              "scene_type": "infographic",
              "search_queries": ["plants metabolism"],
              "search_query_layers": {"l1": ["plants metabolism"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["植物", "代谢"],
              "keywords_en": ["plants", "metabolism"],
              "card_text": "",
              "visual_brief": "illustration of plants affecting metabolism"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    async def fake_pexels_search(self, segment: Segment, query: str):
        return [
            MaterialCandidate(
                id="pexels:weak",
                source_type="pexels",
                media_type="image",
                uri="https://example.com/weak.jpg",
                thumbnail_url="https://example.com/thumb.jpg",
                preview_uri="https://example.com/thumb.jpg",
                width=1080,
                height=1920,
                relevance_score=0.75,
            )
        ]

    async def fake_pixabay_search(self, segment: Segment, query: str):
        return []

    async def fake_judge_scores(self, segment, candidates):
        return [{"id": candidate.id, "score": 0.78, "reason": "Somewhat related."} for candidate in candidates]

    monkeypatch.setattr("cmm.analyzer.llm_analyzer.LLMAnalyzer._request_completion", fake_request_completion)
    monkeypatch.setattr("cmm.fetcher.pexels.PexelsProvider.search", fake_pexels_search)
    monkeypatch.setattr("cmm.fetcher.pixabay.PixabayProvider.search", fake_pixabay_search)
    monkeypatch.setattr("cmm.scorer.SemanticScorer._request_scores", fake_judge_scores)

    result = __import__("asyncio").run(
        match_script(
            MatchInput(
                text="植物会影响身体代谢。",
                output_dir=str(tmp_path / "output"),
                save_candidates=False,
            ),
            settings=settings,
            data_dir=str(data_dir),
        )
    )

    assert result.segments[0].chosen is not None
    assert result.segments[0].chosen.source_type == "data_card"
    manifest = json.loads((tmp_path / "output" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["segments"][0]["use_status"] == "prefer_explainer"
    assert manifest["segments"][0]["review_priority"] == "low"
    assert manifest["segments"][0]["chosen"]["source_label"] == "generated.data_card.health.process"
