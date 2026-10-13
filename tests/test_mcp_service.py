import asyncio
import json
import logging
from pathlib import Path
import sys

import pytest

from cmm.config import Settings
from cmm.models import AnalysisResult, MatchResult, MatchSummary, Segment, SegmentMatch
from cmm.outputs import write_match_outputs


def service(tmp_path, **kwargs):
    from cmm.mcp_service import ScriptMateService
    return ScriptMateService(Settings(), tmp_path / "jobs", **kwargs)


def test_mcp_match_preserves_link_first_defaults_and_outputs(tmp_path, monkeypatch):
    seen = {}

    async def fake_match(match_input, settings, data_dir, **kwargs):
        seen.update(input=match_input, settings=settings)
        kwargs["progress_callback"](1, 1)
        segment = Segment(id=1, text=match_input.text, visual_type="skip")
        result = MatchResult(created_at="2026-10-13", total_segments=1,
                             analysis=AnalysisResult(segments=[segment]),
                             segments=[SegmentMatch(segment=segment, action="skip")],
                             match_summary=MatchSummary(skipped=1),
                             output_dir=match_input.output_dir)
        write_match_outputs(result, result.output_dir)
        return result

    async def run():
        tool = service(tmp_path)
        monkeypatch.setattr("cmm.mcp_service.match_script", fake_match)
        job = tool.start_match("城市发展", "16:9")
        result = await tool.get_result(job["job_id"], wait_seconds=1)
        assert result["status"] == "completed"
        assert result["completed_segments"] == result["total_segments"] == 1
        assert result["segments"] == []  # details are opt-in
        details = await tool.get_result(job["job_id"], offset=0, limit=1)
        assert details["segments"][0]["text"] == "城市发展"
        assert not seen["input"].save_candidates
        assert not any(seen["settings"].downgrade.model_dump().values())
        for name in ("analysis.json", "manifest.json", "summary.md", "review.html", "segments_overview.csv", "segments/001/segment.json"):
            assert (tmp_path / "jobs" / job["job_id"] / name).is_file()
        restarted = service(tmp_path)
        assert (await restarted.get_result(job["job_id"]))["status"] == "completed"

    asyncio.run(run())


def test_mcp_stdio_handshake_from_an_unrelated_directory(tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    config = tmp_path / "config.toml"
    config.write_text('[sources]\nenabled = ["nasa"]\n')

    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "cmm.mcp_server", "--config", str(config), "--output-root", str(tmp_path / "jobs")],
            cwd=str(tmp_path),
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 6
                response = await session.call_tool("doctor", {})
                assert not response.isError
                assert response.structuredContent["mcp"]["transport"] == "stdio"
                assert response.structuredContent["sources"]["enabled"] == ["nasa"]

    asyncio.run(run())


def test_logging_does_not_pollute_stdio(capsys):
    from cmm.logging import configure_logging
    configure_logging(stream=sys.stderr).info("protocol-safe-log")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "protocol-safe-log" in captured.err


def test_package_data_is_available():
    from cmm.paths import data_directory
    assert json.loads((data_directory() / "keyword_mapping.json").read_text(encoding="utf-8-sig"))


def test_http_request_logging_never_exposes_source_key(tmp_path, caplog):
    pytest.importorskip("mcp")
    import httpx
    from cmm.mcp_server import create_server

    async def run():
        caplog.set_level(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.INFO)
        create_server(service(tmp_path))
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get("https://example.org/api/?key=private-provider-key")
        assert "private-provider-key" not in caplog.text

    asyncio.run(run())


def test_match_limits_and_cancellation(tmp_path, monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(30)

    async def run():
        tool = service(tmp_path)
        monkeypatch.setattr("cmm.mcp_service.match_script", slow)
        job = tool.start_match("城市", "9:16")
        with pytest.raises(ValueError, match="running"):
            tool.start_match("另一个", "9:16")
        await tool.cancel_match(job["job_id"])
        assert (await tool.get_result(job["job_id"]))["status"] == "cancelled"
        with pytest.raises(ValueError):
            await tool.get_result("../config.toml")

    asyncio.run(run())


def test_failure_is_persisted_without_api_key(tmp_path, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("Provider rejected private-test-api-key")

    async def run():
        tool = service(tmp_path)
        tool.settings.planner_model.api_key = "private-test-api-key"
        monkeypatch.setattr("cmm.mcp_service.match_script", broken)
        job = tool.start_match("城市", "9:16")
        result = await tool.get_result(job["job_id"], wait_seconds=1)
        assert result["status"] == "failed"
        assert "private-test-api-key" not in json.dumps(result)
        assert "RuntimeError" in result["error"]

    asyncio.run(run())


def test_error_redacts_url_encoded_credentials(tmp_path):
    tool = service(tmp_path)
    tool.settings.sources.pixabay.api_key = "private+key/value"
    message = tool._safe_error(RuntimeError("https://example.org/?key=private%2Bkey%2Fvalue"))
    assert "private" not in message


def test_result_file_symlink_cannot_read_outside_job(tmp_path):
    tool = service(tmp_path)
    job_id = "b" * 32
    folder = tmp_path / "jobs" / job_id
    folder.mkdir()
    private = tmp_path / "private.json"
    private.write_text('{"status":"running","secret":"do-not-read"}')
    (folder / "job.json").symlink_to(private)
    with pytest.raises(ValueError, match="outside"):
        asyncio.run(tool.get_result(job_id))


@pytest.mark.parametrize("text,aspect,top", [("", "9:16", 3), ("x", "bad", 3), ("x", "9:16", 100), ("x" * 20001, "9:16", 3)], ids=["empty", "aspect", "top", "length"])
def test_invalid_match_never_creates_job(tmp_path, text, aspect, top):
    tool = service(tmp_path)
    with pytest.raises(ValueError):
        tool.start_match(text, aspect, top=top)
    assert not list((tmp_path / "jobs").glob("*/job.json"))


def test_restart_reports_unfinished_job_as_interrupted(tmp_path):
    tool = service(tmp_path)
    job_id = "a" * 32
    folder = tmp_path / "jobs" / job_id
    folder.mkdir()
    (folder / "job.json").write_text(json.dumps({"job_id": job_id, "status": "running"}))
    assert asyncio.run(tool.get_result(job_id))["status"] == "interrupted"


def test_progress_callback_covers_skipped_segments(tmp_path, monkeypatch):
    from cmm.pipeline import match_script
    from cmm.models import MatchInput

    async def analysis(*args, **kwargs):
        return AnalysisResult(segments=[Segment(id=i, text="口播", visual_type="skip") for i in (1, 2)])

    monkeypatch.setattr("cmm.pipeline.analyze_script", analysis)
    progress = []
    asyncio.run(match_script(MatchInput(text="口播", output_dir=str(tmp_path), save_candidates=False),
                             Settings(), str(tmp_path),
                             progress_callback=lambda done, total: progress.append((done, total))))
    assert progress == [(0, 2), (1, 2), (2, 2)]


def test_search_validates_provider_and_does_not_call_planner(tmp_path, monkeypatch):
    from cmm.models import SearchResult
    calls = []

    async def search(query, *args, **kwargs):
        calls.append((query, kwargs))
        return SearchResult(query=query, source=kwargs["source"], candidates=[])

    async def run():
        tool = service(tmp_path)
        monkeypatch.setattr("cmm.mcp_service.search_single_query", search)
        result = await tool.search("上海城市", "16:9", source="commons", media_type="image")
        assert result["source"] == "commons"
        with pytest.raises(ValueError):
            await tool.search("城市", "16:9", source="unknown")
        assert len(calls) == 1

    asyncio.run(run())


def test_mcp_protocol_schemas_and_structured_results(tmp_path):
    pytest.importorskip("mcp")
    from cmm.mcp_server import create_server

    async def run():
        server = create_server(service(tmp_path))
        tools = {tool.name: tool for tool in await server.list_tools()}
        assert set(tools) == {"analyze_script", "search_materials", "match_script", "get_result", "cancel_match", "doctor"}
        assert all(tool.outputSchema is not None for tool in tools.values())
        assert "aspect" in tools["match_script"].inputSchema["required"]
        assert tools["match_script"].inputSchema["properties"]["download"]["default"] is False
        assert tools["match_script"].annotations.readOnlyHint is False
        assert tools["get_result"].annotations.readOnlyHint is True
        response = await server.call_tool("doctor", {})
        assert response  # SDK validates the registered output schema

    asyncio.run(run())
