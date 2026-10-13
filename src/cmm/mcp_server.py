"""Local stdio entrypoint; no agent-specific runtime or prompts required."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sys
from typing import Any, Literal

from cmm.config import Settings
from cmm.mcp_service import ScriptMateService


Aspect = Literal["9:16", "16:9", "4:3", "3:4", "1:1"]
Resolution = Literal["4K", "1080", "720"]
Source = Literal["all", "pexels", "pixabay", "coverr", "nasa", "openverse", "commons"]


def create_server(service: ScriptMateService):
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError:
        raise RuntimeError("MCP requires Python 3.10+ and the optional dependency: pip install 'copy-material-matcher[mcp]'.") from None

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield service
        finally:
            await service.close()

    # Some providers put credentials in URL query strings. HTTPX INFO request logs
    # would expose those URLs to the client; server logging must stay above INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    server = FastMCP("ScriptMate", lifespan=lifespan, log_level="WARNING", instructions=(
        "Match short-video scripts to real footage and images. Requires the user's configured model/provider keys. "
        "Start match_script once, then use get_result to wait and read paginated results. "
        "Do not call analyze_script before a full match unless separate analysis is requested. "
        "Keep download and all fallbacks disabled unless requested. Videos require manual clip review."
    ))
    network_read = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=network_read)
    async def analyze_script(text: str, aspect: Aspect) -> dict[str, Any]:
        """Analyze up to 20000 script characters into segments and visual/search strategy. Calls the configured planner model and consumes API quota; does not search materials."""
        return await service.analyze(text, aspect)

    @server.tool(annotations=network_read)
    async def search_materials(query: str, aspect: Aspect, source: Source = "all", top: int = 5,
                               resolution: Resolution = "1080", media_type: Literal["video", "image"] = "video") -> dict[str, Any]:
        """Search real stock sources for a query (max 500 characters, top 1–20). Returns metadata/source links without planner or judge calls. Consumes source API quota; candidates need review."""
        return await service.search(query, aspect, source, top, resolution, media_type)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                            idempotentHint=False, openWorldHint=True))
    async def match_script(text: str, aspect: Aspect, top: int = 3, resolution: Resolution = "1080",
                           download: bool = False, allow_planner_fallback: bool = False,
                           allow_judge_fallback: bool = False, allow_search_fallback: bool = False,
                           allow_generated_fallback: bool = False) -> dict[str, Any]:
        """Start a full material package job and immediately return job_id. One match runs at a time; script max 20000 characters, top 1–20 (minimum effective 3). Calls configured planner/judge and sources, consuming quota. Links first; downloads and fallbacks require explicit opt-in. Poll get_result, do not resubmit to check status."""
        return service.start_match(text, aspect, top, resolution, download, allow_planner_fallback,
                                   allow_judge_fallback, allow_search_fallback, allow_generated_fallback)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    async def get_result(job_id: str, offset: int = 0, limit: int = 0, wait_seconds: float = 0) -> dict[str, Any]:
        """Read job status/progress, warnings and output paths without API calls. wait_seconds 0–30 waits for completion. limit=0 returns summary only; set limit 1–20 for paginated segment selections, scores, licenses and source links. Completed results survive restarts."""
        return await service.get_result(job_id, offset, limit, wait_seconds)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                            idempotentHint=True, openWorldHint=False))
    async def cancel_match(job_id: str) -> dict[str, Any]:
        """Cancel a running match. Keep partial output files. In-flight provider requests may already have consumed quota. Does not delete completed packages."""
        return await service.cancel_match(job_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def doctor() -> dict[str, Any]:
        """Inspect config, configured models/source keys (presence only), vision scope and local paths. No network calls; does not prove credentials are valid."""
        return service.doctor()

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="ScriptMate local MCP server (stdio). Requires Python 3.10+ and the [mcp] extra.")
    parser.add_argument("--config", type=Path, help="User-owned config.toml; use an absolute path in the MCP client.")
    parser.add_argument("--output-root", type=Path, default=Path.home() / ".local" / "share" / "scriptmate" / "jobs")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("MCP requires Python 3.10+. The regular ScriptMate CLI still supports Python 3.9.")
    config = (args.config or Path.home() / ".config" / "scriptmate" / "config.toml").expanduser().resolve()
    if not config.is_file():
        parser.error("Configuration file does not exist: {}. Run scriptmate setup-mcp --config <path>.".format(config))
    from cmm.logging import configure_logging
    configure_logging(stream=sys.stderr)
    try:
        # An explicit path prevents GUI-client working directories selecting a different config.
        settings = Settings.from_file(str(config))
        base = config.parent
        for owner, field in ((settings.library, "root"), (settings.library, "metadata"), (settings.output, "cache_dir")):
            value = getattr(owner, field)
            if value:
                path = Path(value).expanduser()
                setattr(owner, field, str((base / path).resolve() if not path.is_absolute() else path.resolve()))
        service = ScriptMateService(settings, args.output_root, config)
        create_server(service).run(transport="stdio")
    except Exception as exc:
        # Config parse errors may contain a TOML line with secrets: never print the raw exception.
        parser.exit(1, "ScriptMate MCP could not start ({}). Check Python, [mcp] dependencies and config syntax.\n".format(type(exc).__name__))


if __name__ == "__main__":
    main()
