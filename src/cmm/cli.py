from __future__ import annotations

import asyncio
import json
import os
import platform
from pathlib import Path
from typing import Optional

import typer

from cmm import __version__
from cmm.cache import FileCache
from cmm.config import Settings
from cmm.logging import configure_logging
from cmm.models import MatchInput, model_dump_compat
from cmm.pipeline import analyze_script, match_script, search_single_query


app = typer.Typer(
    help=(
        "ScriptMate CLI：文案驱动的高质量素材匹配工具。\n"
        "默认策略：上下文优先、国家/叙事对象一致、每段至少 3 条真实候选、默认不降级、链接优先。"
    ),
    no_args_is_help=True,
)


def _read_text(text: Optional[str], file: Optional[Path]) -> str:
    if text:
        return text
    if file:
        return file.read_text(encoding="utf-8")
    return ""


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return "{0}...{1}".format(value[:4], value[-4:])


def _resolve_api_key(config_value: str, env_names) -> str:
    if config_value:
        return config_value
    for name in env_names:
        value = os.getenv(name, "")
        if value:
            return value
    return ""


def _render_config_template(
    planner_provider: str,
    planner_model: str,
    planner_api_key: str,
    planner_base_url: str,
    judge_provider: str,
    judge_model: str,
    judge_api_key: str,
    judge_base_url: str,
    pexels_api_key: str,
    pixabay_api_key: str,
) -> str:
    return """[planner_model]
provider = "{planner_provider}"
model = "{planner_model}"
api_key = "{planner_api_key}"
base_url = "{planner_base_url}"
timeout_seconds = 30
max_retries = 1

[judge_model]
provider = "{judge_provider}"
model = "{judge_model}"
api_key = "{judge_api_key}"
base_url = "{judge_base_url}"
timeout_seconds = 30
max_retries = 1

[sources]
enabled = ["pexels", "pixabay"]

[sources.pexels]
api_key = "{pexels_api_key}"
base_url = ""

[sources.pixabay]
api_key = "{pixabay_api_key}"
base_url = ""

[matching]
top_results = 3
search_pool_size = 8
min_score = 0.55
strong_score = 0.70
video_min_resolution = 1080
video_orientation = "vertical"

[generation]
charts = true
ai_images = false
chart_style = "dark_professional"

[library]
root = ""
metadata = ""

[cards]
width = 1080
height = 1920
theme = "atlas"

[output]
format = "both"
download_quality = "hd"
cache_dir = ""
""".format(
        planner_provider=planner_provider,
        planner_model=planner_model,
        planner_api_key=planner_api_key,
        planner_base_url=planner_base_url,
        judge_provider=judge_provider,
        judge_model=judge_model,
        judge_api_key=judge_api_key,
        judge_base_url=judge_base_url,
        pexels_api_key=pexels_api_key,
        pixabay_api_key=pixabay_api_key,
    )


def _build_doctor_payload(settings: Settings, config_file: Optional[Path]) -> dict:
    planner_key = _resolve_api_key(settings.planner_model.api_key, ["PLANNER_MODEL_API_KEY", "OPENAI_API_KEY"])
    judge_key = _resolve_api_key(settings.judge_model.api_key, ["JUDGE_MODEL_API_KEY", "OPENAI_API_KEY"])
    pexels_key = _resolve_api_key(settings.sources.pexels.api_key, ["PEXELS_API_KEY"])
    pixabay_key = _resolve_api_key(settings.sources.pixabay.api_key, ["PIXABAY_API_KEY"])
    root = Path.cwd()
    return {
        "version": __version__,
        "python": {
            "version": platform.python_version(),
            "supported": tuple(__import__("sys").version_info[:2]) >= (3, 9),
        },
        "config": {
            "path": str(config_file or (root / "config.toml")),
            "exists": bool(config_file and config_file.exists()) or (not config_file and (root / "config.toml").exists()),
        },
        "planner_model": {
            "provider": settings.planner_model.provider,
            "model": settings.planner_model.model,
            "base_url": settings.planner_model.base_url,
            "api_key_configured": bool(planner_key),
        },
        "judge_model": {
            "provider": settings.judge_model.provider,
            "model": settings.judge_model.model,
            "base_url": settings.judge_model.base_url,
            "api_key_configured": bool(judge_key),
        },
        "sources": {
            "enabled": settings.sources.enabled,
            "pexels_api_key_configured": bool(pexels_key),
            "pixabay_api_key_configured": bool(pixabay_key),
            "extra_sources": [item.name for item in settings.sources.configured_external_sources()],
        },
        "matching": {
            "top_results": settings.matching.top_results,
            "search_pool_size": settings.matching.search_pool_size,
            "video_min_resolution": settings.matching.video_min_resolution,
            "video_orientation": settings.matching.video_orientation,
        },
        "output": {
            "cache_dir": settings.output.cache_dir or "",
        },
    }


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show ScriptMate CLI version and exit."),
):
    if version:
        typer.echo("ScriptMate CLI {0}".format(__version__))
        raise typer.Exit()


@app.command("init")
def init_config(
    config_file: Path = typer.Option(Path("config.toml"), "--config", help="Path to write the generated config file."),
    force: bool = typer.Option(False, "--force", help="Overwrite the target config file if it already exists."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Write config using defaults and passed flags only."),
    planner_provider: str = typer.Option("openai", help="Planner model provider."),
    planner_model: str = typer.Option("gpt-4.1-mini", help="Planner model name."),
    planner_base_url: str = typer.Option("https://api.openai.com/v1", help="Planner model base URL."),
    judge_provider: str = typer.Option("openai", help="Judge model provider."),
    judge_model: str = typer.Option("gpt-4o-mini", help="Judge model name."),
    judge_base_url: str = typer.Option("https://api.openai.com/v1", help="Judge model base URL."),
    planner_api_key: str = typer.Option("", help="Planner model API key. Leave blank to prefer environment variables."),
    judge_api_key: str = typer.Option("", help="Judge model API key. Leave blank to prefer environment variables."),
    pexels_api_key: str = typer.Option("", help="Pexels API key. Leave blank to prefer environment variables."),
    pixabay_api_key: str = typer.Option("", help="Pixabay API key. Leave blank to prefer environment variables."),
):
    if config_file.exists() and not force:
        raise typer.BadParameter("Config file already exists. Use --force to overwrite.")

    if not non_interactive:
        planner_provider = typer.prompt("Planner provider", default=planner_provider)
        planner_model = typer.prompt("Planner model", default=planner_model)
        planner_base_url = typer.prompt("Planner base URL", default=planner_base_url)
        planner_api_key = typer.prompt(
            "Planner API key (leave blank to use env)",
            default=planner_api_key,
            hide_input=True,
            show_default=False,
        )
        judge_provider = typer.prompt("Judge provider", default=judge_provider)
        judge_model = typer.prompt("Judge model", default=judge_model)
        judge_base_url = typer.prompt("Judge base URL", default=judge_base_url)
        judge_api_key = typer.prompt(
            "Judge API key (leave blank to use env)",
            default=judge_api_key,
            hide_input=True,
            show_default=False,
        )
        pexels_api_key = typer.prompt(
            "Pexels API key (leave blank to use env)",
            default=pexels_api_key,
            hide_input=True,
            show_default=False,
        )
        pixabay_api_key = typer.prompt(
            "Pixabay API key (leave blank to use env)",
            default=pixabay_api_key,
            hide_input=True,
            show_default=False,
        )

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        _render_config_template(
            planner_provider=planner_provider,
            planner_model=planner_model,
            planner_api_key=planner_api_key,
            planner_base_url=planner_base_url,
            judge_provider=judge_provider,
            judge_model=judge_model,
            judge_api_key=judge_api_key,
            judge_base_url=judge_base_url,
            pexels_api_key=pexels_api_key,
            pixabay_api_key=pixabay_api_key,
        ),
        encoding="utf-8",
    )
    typer.echo("Wrote config: {0}".format(config_file))
    typer.echo("Next step: run `scriptmate doctor --config {0}` to verify your environment.".format(config_file))


@app.command("doctor")
def doctor(
    config_file: Optional[Path] = typer.Option(None, "--config", help="Config file to inspect."),
):
    settings = Settings.from_file(str(config_file) if config_file else None)
    typer.echo(json.dumps(_build_doctor_payload(settings, config_file), ensure_ascii=False, indent=2))


@app.command("config-show")
def config_show(
    config_file: Optional[Path] = typer.Option(None, "--config", help="Config file to inspect."),
):
    settings = Settings.from_file(str(config_file) if config_file else None)
    payload = {
        "planner_model": {
            "provider": settings.planner_model.provider,
            "model": settings.planner_model.model,
            "base_url": settings.planner_model.base_url,
            "api_key": _mask(_resolve_api_key(settings.planner_model.api_key, ["PLANNER_MODEL_API_KEY", "OPENAI_API_KEY"])),
        },
        "judge_model": {
            "provider": settings.judge_model.provider,
            "model": settings.judge_model.model,
            "base_url": settings.judge_model.base_url,
            "api_key": _mask(_resolve_api_key(settings.judge_model.api_key, ["JUDGE_MODEL_API_KEY", "OPENAI_API_KEY"])),
        },
        "sources": {
            "enabled": settings.sources.enabled,
            "pexels_api_key": _mask(_resolve_api_key(settings.sources.pexels.api_key, ["PEXELS_API_KEY"])),
            "pixabay_api_key": _mask(_resolve_api_key(settings.sources.pixabay.api_key, ["PIXABAY_API_KEY"])),
            "extra_sources": [item.name for item in settings.sources.configured_external_sources()],
        },
        "matching": model_dump_compat(settings.matching),
        "output": model_dump_compat(settings.output),
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("match")
def match(
    text: Optional[str] = typer.Argument(None, help="Inline script text. Prefer --file for long scripts."),
    file: Optional[Path] = typer.Option(None, "--file", help="Path to a script text file."),
    output_dir: Path = typer.Option(..., "-o", "--output", help="Directory where the material package will be written."),
    top: int = typer.Option(3, "--top", help="Final shortlist size per segment. Minimum effective value is 3."),
    aspect: str = typer.Option("9:16", "--aspect", help="Target aspect ratio: 9:16, 16:9, or 1:1."),
    resolution: str = typer.Option("1080", "--resolution", help="Preferred minimum resolution tier: 4K, 1080, or 720."),
    style: str = typer.Option("clean", "--style", help="Output style hint used by generated cards or charts."),
    library_root: Optional[Path] = typer.Option(None, "--library-root", help="Optional local material library root."),
    library_meta: Optional[Path] = typer.Option(None, "--library-meta", help="Optional metadata file for the local material library."),
    download: bool = typer.Option(False, "--download", help="Download chosen and alternative assets to local files."),
    allow_planner_fallback: bool = typer.Option(False, "--allow-planner-fallback", help="Allow local heuristic planner fallback if the planner model fails."),
    allow_judge_fallback: bool = typer.Option(False, "--allow-judge-fallback", help="Allow heuristic judge fallback if multimodal scoring fails."),
    allow_search_fallback: bool = typer.Option(False, "--allow-search-fallback", help="Allow extra fallback search when strict real-candidate search is insufficient."),
    allow_generated_fallback: bool = typer.Option(False, "--allow-generated-fallback", help="Allow generated cards or charts as fallback."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logs."),
    config_file: Optional[Path] = typer.Option(None, "--config", help="Config file path. Defaults to ./config.toml if present."),
):
    configure_logging(verbose)
    source_text = _read_text(text, file)
    if not source_text.strip():
        raise typer.BadParameter("Provide script text or --file.")
    settings = Settings.from_file(str(config_file) if config_file else None)
    settings.downgrade.planner_fallback = allow_planner_fallback
    settings.downgrade.judge_fallback = allow_judge_fallback
    settings.downgrade.search_fallback = allow_search_fallback
    settings.downgrade.generated_fallback = allow_generated_fallback
    package_root = Path(__file__).resolve().parents[2]
    result = asyncio.run(
        match_script(
            MatchInput(
                text=source_text,
                aspect=aspect,
                resolution=resolution,
                style=style,
                top_results=max(top, 3),
                output_dir=str(output_dir),
                save_candidates=download,
            ),
            settings=settings,
            data_dir=str(package_root / "data"),
            library_root=str(library_root) if library_root else settings.library.root or None,
            library_meta=str(library_meta) if library_meta else settings.library.metadata or None,
        )
    )
    typer.echo(json.dumps(model_dump_compat(result), ensure_ascii=False, indent=2))


@app.command("analyze")
def analyze(
    text: Optional[str] = typer.Argument(None, help="Inline script text. Prefer --file for long scripts."),
    file: Optional[Path] = typer.Option(None, "--file", help="Path to a script text file."),
    aspect: str = typer.Option("9:16", "--aspect", help="Target aspect ratio: 9:16, 16:9, or 1:1."),
    output_dir: Optional[Path] = typer.Option(None, "-o", "--output", help="Optional directory where analysis.json will be written."),
    allow_planner_fallback: bool = typer.Option(False, "--allow-planner-fallback", help="Allow local heuristic planner fallback if the planner model fails."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logs."),
    config_file: Optional[Path] = typer.Option(None, "--config", help="Config file path. Defaults to ./config.toml if present."),
):
    configure_logging(verbose)
    source_text = _read_text(text, file)
    if not source_text.strip():
        raise typer.BadParameter("Provide script text or --file.")
    settings = Settings.from_file(str(config_file) if config_file else None)
    settings.downgrade.planner_fallback = allow_planner_fallback
    cache_root = settings.output.cache_dir or str((output_dir or Path.cwd()) / "cache")
    cache = FileCache(cache_root)
    result = asyncio.run(analyze_script(source_text, settings, cache, aspect=aspect))
    payload = model_dump_compat(result)
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "analysis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query for a single material probe."),
    top: int = typer.Option(5, "--top", help="How many candidates to return."),
    source: str = typer.Option("all", "--source", help="Material provider: all, pexels, or pixabay."),
    aspect: str = typer.Option("9:16", "--aspect", help="Target aspect ratio: 9:16, 16:9, or 1:1."),
    resolution: str = typer.Option("1080", "--resolution", help="Preferred minimum resolution tier: 4K, 1080, or 720."),
    output_dir: Optional[Path] = typer.Option(None, "-o", "--output", help="Optional directory where search.json will be written."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logs."),
    config_file: Optional[Path] = typer.Option(None, "--config", help="Config file path. Defaults to ./config.toml if present."),
):
    configure_logging(verbose)
    settings = Settings.from_file(str(config_file) if config_file else None)
    cache_root = settings.output.cache_dir or str((output_dir or Path.cwd()) / "cache")
    cache = FileCache(cache_root)
    package_root = Path(__file__).resolve().parents[2]
    result = asyncio.run(
        search_single_query(
            query,
            settings,
            cache,
            str(package_root / "data"),
            source=source,
            top_k=top,
            aspect=aspect,
            resolution=resolution,
        )
    )
    payload = model_dump_compat(result)
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "search.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
