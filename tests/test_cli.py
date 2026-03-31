from pathlib import Path

from typer.testing import CliRunner

from cmm.cli import app
from cmm.models import AnalysisResult, MatchResult, MatchSummary, SearchResult, Segment


runner = CliRunner()


def _write_realish_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[planner_model]
provider = "openai"
model = "gpt-4.1-mini"
api_key = "x"
base_url = "https://example.com/v1"

[judge_model]
provider = "openai"
model = "gpt-4o-mini"
api_key = "x"
base_url = "https://example.com/v1"
""".strip(),
        encoding="utf-8",
    )
    return config


def test_analyze_command_outputs_analysis_json(tmp_path: Path, monkeypatch):
    config = _write_realish_config(tmp_path)

    async def fake_analyze_script(text, settings, cache, aspect="9:16"):
        return AnalysisResult(
            segments=[Segment(id=1, text=text, visual_type="text_card", scene_type="text_card", segment_role="summary")],
            target_aspect=aspect,
        )

    monkeypatch.setattr("cmm.cli.analyze_script", fake_analyze_script)
    result = runner.invoke(app, ["analyze", "大家好，今天聊经济增长。最后总结一下。", "-o", str(tmp_path / "out"), "--config", str(config)])
    assert result.exit_code == 0
    assert (tmp_path / "out" / "analysis.json").exists()


def test_search_command_outputs_json(tmp_path: Path, monkeypatch):
    config = _write_realish_config(tmp_path)
    captured = {}

    async def fake_search_single_query(query, settings, cache, data_dir, source="all", top_k=5, aspect="9:16", resolution="1080"):
        captured["aspect"] = aspect
        captured["resolution"] = resolution
        return SearchResult(query=query, source=source, candidates=[])

    monkeypatch.setattr("cmm.cli.search_single_query", fake_search_single_query)
    result = runner.invoke(app, ["search", "economic growth", "--aspect", "16:9", "--resolution", "4K", "-o", str(tmp_path / "out"), "--config", str(config)])
    assert result.exit_code == 0
    assert (tmp_path / "out" / "search.json").exists()
    assert captured["aspect"] == "16:9"
    assert captured["resolution"] == "4K"


def test_match_command_requires_input():
    result = runner.invoke(app, ["match", "-o", "tmp-out"])
    assert result.exit_code != 0


def test_match_command_defaults_to_link_only_outputs(tmp_path: Path, monkeypatch):
    config = _write_realish_config(tmp_path)
    captured = {}

    async def fake_match_script(match_input, settings, data_dir, library_root=None, library_meta=None):
        captured["save_candidates"] = match_input.save_candidates
        captured["top_results"] = match_input.top_results
        captured["resolution"] = match_input.resolution
        return MatchResult(
            created_at="2026-03-30T00:00:00+00:00",
            total_segments=0,
            analysis=AnalysisResult(segments=[]),
            segments=[],
            match_summary=MatchSummary(),
            output_dir=str(tmp_path / "out"),
        )

    monkeypatch.setattr("cmm.cli.match_script", fake_match_script)
    result = runner.invoke(app, ["match", "test script", "-o", str(tmp_path / "out"), "--config", str(config)])

    assert result.exit_code == 0
    assert captured["save_candidates"] is False
    assert captured["top_results"] == 3
    assert captured["resolution"] == "1080"


def test_init_command_writes_config_non_interactively(tmp_path: Path):
    target = tmp_path / "config.toml"
    result = runner.invoke(
        app,
        [
            "init",
            "--config",
            str(target),
            "--non-interactive",
            "--planner-model",
            "gpt-4.1-mini",
            "--judge-model",
            "gpt-4o-mini",
            "--pexels-api-key",
            "pexels-demo",
        ],
    )
    assert result.exit_code == 0
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert 'model = "gpt-4.1-mini"' in content
    assert 'api_key = "pexels-demo"' in content
    assert 'search_pool_size = 8' in content


def test_doctor_and_config_show_commands_output_expected_fields(tmp_path: Path):
    config = _write_realish_config(tmp_path)
    result_doctor = runner.invoke(app, ["doctor", "--config", str(config)])
    result_show = runner.invoke(app, ["config-show", "--config", str(config)])

    assert result_doctor.exit_code == 0
    assert result_show.exit_code == 0
    assert '"planner_model"' in result_doctor.stdout
    assert '"matching"' in result_doctor.stdout
    assert '"api_key"' in result_show.stdout
    assert '"api_key": "x"' not in result_show.stdout
