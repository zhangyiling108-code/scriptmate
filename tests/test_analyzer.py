from cmm.analyzer.llm_analyzer import LLMAnalyzer
from cmm.config import ModelSettings
from cmm.exceptions import AnalyzerError


def test_analyzer_outputs_roles_and_visual_types(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1")
    )

    async def fake_request_completion(self, prompt: str) -> str:
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
              "segment_role": "data_point",
              "visual_type": "data_card",
              "scene_type": "infographic",
              "search_queries": ["gdp growth"],
              "search_query_layers": {"l1": ["gdp growth"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["GDP"],
              "keywords_en": ["gdp growth"],
              "card_text": "近年来我国GDP持续增长",
              "visual_brief": "chart"
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

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", fake_request_completion)
    result = __import__("asyncio").run(
        analyzer.analyze("大家好，今天聊经济增长。近年来我国GDP持续增长。最后总结一下核心观点。", "9:16")
    )

    assert len(result.segments) == 3
    assert result.segments[0].visual_type == "skip"
    assert result.segments[0].segment_role == "hook"
    assert result.segments[1].visual_type == "data_card"
    assert result.segments[1].scene_type == "infographic"
    assert result.segments[2].visual_type == "stock_image"
    assert result.segments[2].scene_type == "infographic"
    assert result.segments[2].card_text == ""
    assert "l1" in result.segments[1].search_query_layers
    assert result.segments[1].narrative_subject
    assert result.segments[1].context_statement
    assert result.segments[1].context_tags
    assert "context" in result.segments[1].search_query_layers


def test_analyzer_prompt_requires_english_first_stock_queries():
    analyzer = LLMAnalyzer(
        ModelSettings(provider="deepseek", model="deepseek-v4-flash", api_key="x", base_url="https://example.com")
    )

    prompt = analyzer._build_prompt("中国新能源汽车出口增长。", "9:16")

    assert "translate the full script internally into natural English" in prompt
    assert "never Chinese" in prompt
    assert "Do not use text_card" in prompt
    assert "electric vehicle factory assembly line" in prompt


def test_analyzer_filters_chinese_search_queries_from_model_payload(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="deepseek", model="deepseek-v4-flash", api_key="x", base_url="https://example.com")
    )

    async def fake_request_completion(self, prompt: str) -> str:
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "中国新能源汽车出口增长。",
              "segment_role": "claim",
              "visual_type": "stock_video",
              "scene_type": "b_roll",
              "search_queries": ["新能源汽车出口", "electric vehicle export port"],
              "search_query_layers": {"l1": ["中国新能源汽车出口"], "l2": ["car export terminal"], "l3": [], "l4": []},
              "keywords_cn": ["新能源汽车", "出口"],
              "keywords_en": ["new energy vehicle", "export"],
              "card_text": "",
              "visual_brief": "electric vehicle exports at port",
              "narrative_subject": "China electric vehicle export growth",
              "context_statement": "Chinese electric vehicle exports are growing.",
              "context_tags": ["中国", "china", "electric vehicle", "export"]
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", fake_request_completion)

    result = __import__("asyncio").run(analyzer.analyze("中国新能源汽车出口增长。", "9:16"))
    segment = result.segments[0]
    all_queries = segment.search_queries + sum(segment.search_query_layers.values(), [])

    assert "electric vehicle export port" in segment.search_queries
    assert "car export terminal" in segment.search_query_layers["l2"]
    assert all("新能源" not in query and "中国" not in query for query in all_queries)
    assert "china" in [tag.lower() for tag in segment.context_tags]


def test_analyzer_falls_back_to_heuristic_when_remote_fails(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1"),
        allow_fallback=True,
    )

    async def failing_request_completion(self, prompt: str) -> str:
        raise AnalyzerError("upstream timeout")

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", failing_request_completion)
    result = __import__("asyncio").run(
        analyzer.analyze("大家好，今天聊经济增长。植物会影响身体代谢。最后总结一下。", "9:16")
    )

    assert result.overall_style == "heuristic fallback"
    assert len(result.segments) == 3
    assert result.segments[0].visual_type == "skip"
    assert result.segments[1].visual_type in {"stock_video", "data_card"}
    assert result.segments[2].visual_type == "stock_video"


def test_analyzer_falls_back_to_heuristic_on_generic_network_error(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1"),
        allow_fallback=True,
    )

    async def failing_request_completion(self, prompt: str) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", failing_request_completion)
    result = __import__("asyncio").run(
        analyzer.analyze("大家好，今天聊经济增长。最后总结一下。", "9:16")
    )

    assert result.overall_style == "heuristic fallback"
    assert result.segments[0].visual_type == "skip"
    assert result.segments[1].visual_type == "stock_video"


def test_analyzer_raises_when_remote_fails_and_fallback_is_disabled(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1")
    )

    async def failing_request_completion(self, prompt: str) -> str:
        raise AnalyzerError("upstream timeout")

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", failing_request_completion)

    try:
        __import__("asyncio").run(analyzer.analyze("大家好，今天聊经济增长。", "9:16"))
    except AnalyzerError as exc:
        assert "invalid structured output" in str(exc)
        assert exc.__cause__ is not None
        assert "upstream timeout" in str(exc.__cause__)
    else:
        raise AssertionError("Expected AnalyzerError when fallback is disabled.")


def test_analyzer_forces_explanatory_metabolism_segments_to_data_card(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1")
    )

    async def fake_request_completion(self, prompt: str) -> str:
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "植物会影响身体代谢。",
              "segment_role": "explanation",
              "visual_type": "stock_image",
              "scene_type": "infographic",
              "search_queries": ["plants metabolism"],
              "search_query_layers": {"l1": ["plants metabolism"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["植物", "代谢"],
              "keywords_en": ["plants", "metabolism"],
              "card_text": "",
              "visual_brief": "plants and metabolism"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", fake_request_completion)
    result = __import__("asyncio").run(analyzer.analyze("植物会影响身体代谢。", "9:16"))

    assert result.segments[0].visual_type == "data_card"
    assert result.segments[0].scene_type == "infographic"


def test_analyzer_forces_economic_causal_segments_to_data_card(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1")
    )

    async def fake_request_completion(self, prompt: str) -> str:
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "经济增长会影响消费与投资信心。",
              "segment_role": "claim",
              "visual_type": "stock_video",
              "scene_type": "b_roll",
              "search_queries": ["economic growth confidence"],
              "search_query_layers": {"l1": ["economic growth confidence"], "l2": [], "l3": [], "l4": []},
              "keywords_cn": ["经济增长", "消费", "投资"],
              "keywords_en": ["economic growth", "consumption", "investment"],
              "card_text": "",
              "visual_brief": "economic cause effect"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", fake_request_completion)
    result = __import__("asyncio").run(analyzer.analyze("经济增长会影响消费与投资信心。", "9:16"))

    assert result.segments[0].visual_type == "data_card"
    assert result.segments[0].scene_type == "infographic"


def test_analyzer_keeps_concrete_economic_city_scene_as_stock_video(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1")
    )

    async def fake_request_completion(self, prompt: str) -> str:
        return """
        {
          "segments": [
            {
              "id": 1,
              "text": "城市天际线、高楼与繁忙车流，展现现代经济活力。",
              "segment_role": "claim",
              "visual_type": "stock_video",
              "scene_type": "b_roll",
              "search_queries": ["city skyline traffic economy"],
              "search_query_layers": {"l1": ["city skyline"], "l2": ["urban economy"], "l3": [], "l4": []},
              "keywords_cn": ["城市", "高楼", "车流", "经济活力"],
              "keywords_en": ["city skyline", "traffic", "economy"],
              "card_text": "",
              "visual_brief": "real city economy footage"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", fake_request_completion)
    result = __import__("asyncio").run(analyzer.analyze("城市天际线、高楼与繁忙车流，展现现代经济活力。", "9:16"))

    assert result.segments[0].visual_type == "stock_video"
    assert result.segments[0].scene_type == "b_roll"


def test_analyzer_applies_document_context_to_segments(monkeypatch):
    analyzer = LLMAnalyzer(
        ModelSettings(provider="openai", model="gpt-4.1-mini", api_key="x", base_url="https://example.com/v1")
    )

    async def fake_request_completion(self, prompt: str) -> str:
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
              "search_query_layers": {"l1": ["high speed rail"], "l2": ["rail infrastructure"], "l3": [], "l4": []},
              "keywords_cn": ["高铁"],
              "keywords_en": ["high speed rail"],
              "card_text": "",
              "visual_brief": "rail growth"
            }
          ],
          "overall_style": "clean documentary",
          "target_aspect": "9:16"
        }
        """.strip()

    monkeypatch.setattr(LLMAnalyzer, "_request_completion", fake_request_completion)
    result = __import__("asyncio").run(analyzer.analyze("中国经济发展二十年。高铁里程从零到四万公里。", "9:16"))

    segment = result.segments[0]
    assert "china" in " ".join(segment.context_tags).lower()
    assert "economy" in segment.narrative_subject.lower()
    assert any("china" in query.lower() for query in segment.search_queries)
