"""Interactive onboarding and a credential-free MCP connection check."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import click
import typer

from cmm.config import JudgeSettings, ModelSettings, Settings, SourcesSettings, model_supports_image_input


DEFAULT_CONFIG = Path.home() / ".config" / "scriptmate" / "config.toml"
DEFAULT_OUTPUT = Path.home() / ".local" / "share" / "scriptmate" / "jobs"


def readiness(settings: Settings, config_dir: Path | None = None) -> dict[str, Any]:
    available = [name for name in settings.sources.enabled
                 if name in {"nasa", "commons", "openverse"}
                 or (name in {"pexels", "pixabay", "coverr"} and getattr(settings.sources, name).api_key)]
    warnings = []
    models_ready = True
    for role, model in (("planner", settings.planner_model), ("judge", settings.judge_model)):
        if not model.api_key or not model.base_url or not model.model:
            models_ready = False
            warnings.append("{}: 模型、端点或密钥未配置；请重新配置或注入环境变量。".format(role))
    search_ready = bool(available)
    library_root = Path(settings.library.root).expanduser()
    if config_dir and not library_root.is_absolute():
        library_root = config_dir / library_root
    local_ready = bool(settings.library.root and library_root.is_dir())
    if not search_ready and not local_ready:
        warnings.append("sources: 尚无可搜索来源；可启用 nasa/commons，或配置素材源密钥。")
    for name in settings.sources.enabled:
        if name in {"pexels", "pixabay", "coverr"} and not getattr(settings.sources, name).api_key:
            warnings.append("sources.{}: 已启用但缺少密钥。".format(name))
    visual_ready = bool(settings.judge.vision and model_supports_image_input(settings.judge_model))
    if settings.judge.vision and not visual_ready:
        models_ready = False
        warnings.append("judge.vision: 已开启，但当前模型配置无法使用图片输入；请核对模型名称和 supports_vision。")
    requires_visual = settings.judge.require_visual_evidence or settings.judge_model.provider.lower() == "typesafe"
    if requires_visual and not visual_ready:
        warnings.append("judge.vision: 主选要求图片核验，当前未启用；候选保留人工复核。")
    matching = models_ready and (search_ready or local_ready)
    return {"search_ready": search_ready, "available_sources": available,
            "matching_configured": matching,
            "automatic_primary_configured": matching and (not requires_visual or visual_ready),
            "credentials_verified": False, "warnings": warnings}


def launch_config(config: Path, output_root: Path) -> dict[str, Any]:
    # Bind to this installation, rather than an unrelated executable on PATH.
    executable = Path(sys.executable).absolute()
    entrypoint = executable.parent / ("scriptmate-mcp.exe" if os.name == "nt" else "scriptmate-mcp")
    command = str(entrypoint if entrypoint.is_file() else executable)
    args = [] if entrypoint.is_file() else ["-m", "cmm.mcp_server"]
    args.extend(["--config", str(config), "--output-root", str(output_root)])
    return {"command": command, "args": args}


def _new_private_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)


def _export(path: Path, content: str) -> Path:
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == content:
                return path
        except (UnicodeError, OSError):
            pass
        path = path.with_name(path.stem + "-" + uuid4().hex[:8] + path.suffix)
    _new_private_file(path, content)
    return path


def _render(settings: Settings) -> str:
    sections = {
        "planner_model": settings.planner_model.model_dump(exclude_none=True),
        "judge_model": settings.judge_model.model_dump(exclude_none=True),
        "sources": {"enabled": settings.sources.enabled},
        "sources.pexels": settings.sources.pexels.model_dump(),
        "sources.pixabay": settings.sources.pixabay.model_dump(),
        "sources.nasa": settings.sources.nasa.model_dump(),
        "sources.commons": settings.sources.commons.model_dump(),
        "judge": settings.judge.model_dump(),
        "generation": {"charts": False, "ai_images": False},
        "library": {"root": "", "metadata": ""},
    }
    lines = ["# ScriptMate MCP 私有配置；不要提交或分享此文件。", ""]
    for section, values in sections.items():
        lines.append("[{}]".format(section))
        for key, value in values.items():
            lines.append("{} = {}".format(key, json.dumps(value, ensure_ascii=False)))
        lines.append("")
    return "\n".join(lines)


def _model(label: str, default: ModelSettings | None = None) -> ModelSettings:
    typer.echo("\n{}：1) DeepSeek  2) 其他 OpenAI 兼容服务".format(label))
    choice = typer.prompt("服务类型", default="1", type=click.Choice(["1", "2"]))
    if choice == "1":
        provider, endpoint, model = "deepseek", "https://api.deepseek.com", "deepseek-flash"
    else:
        provider = "compatible"
        endpoint = typer.prompt("API 端点（例如 https://your-provider.example/v1）").strip().rstrip("/")
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise typer.BadParameter("端点须为不含密钥、用户名和查询参数的 HTTP(S) 地址。")
        model = default.model if default else ""
    model = typer.prompt("模型名称（请以供应商账户支持的名称为准）", default=model or None).strip()
    key = typer.prompt("API Key（隐藏输入；留空使用环境变量）", default="", hide_input=True, show_default=False).strip()
    return ModelSettings(provider=provider, model=model, base_url=endpoint, api_key=key)


def _show_status(status: dict) -> None:
    typer.echo("\n搜索配置：{}；完整匹配配置：{}。".format(
        "可用" if status["search_ready"] else "待补充", "已填写" if status["matching_configured"] else "待补充"))
    for warning in status["warnings"]:
        typer.echo("- " + warning)
    typer.echo("密钥有效性与真实接口尚未验证；本步骤不会消耗模型或素材源额度。")


def shell_command(parts: list[str], windows: bool | None = None) -> str:
    if windows is None:
        windows = os.name == "nt"
    if windows:
        # PowerShell literals: operators and $ expansion must remain part of paths.
        return "& " + " ".join("'" + part.replace("'", "''") + "'" for part in parts)
    return shlex.join(parts)


def _setup_mcp(config: Path, output_root: Path, non_interactive: bool, search_only: bool, reconfigure: bool) -> None:
    config = config.expanduser().absolute()
    output_root = output_root.expanduser().absolute()
    typer.echo("ScriptMate MCP 配置向导：密钥仅保存在你的本机。")
    if config.exists() and not reconfigure:
        typer.echo("已有配置，将保留内容并重新生成接入文件：{}".format(config))
    else:
        # Do not copy environment credentials into a template without an explicit entry.
        # Construct only validated defaults; BaseSettings would read unrelated
        # environment routes, potentially exposing their secrets in validation errors.
        settings = Settings.model_construct(planner_model=ModelSettings(), judge_model=ModelSettings(),
                                            sources=SourcesSettings(), judge=JudgeSettings(), prefilter_model=None)
        settings.sources.enabled = ["nasa", "commons"]
        settings.judge.require_visual_evidence = True
        if not non_interactive:
            if not search_only:
                typer.echo("\n1) 完整文案匹配（需要自己的模型 API 额度）  2) 仅搜索公开素材（无需模型密钥）")
                search_only = typer.prompt("使用方式", default="1", type=click.Choice(["1", "2"])) == "2"
            if not search_only:
                settings.planner_model = _model("第 1 步 / 规划模型")
                if typer.confirm("评分复用上述 API 服务、模型与密钥？", default=True):
                    settings.judge_model = settings.planner_model.model_copy(deep=True)
                else:
                    settings.judge_model = _model("评分模型", settings.planner_model)
                typer.echo("图片核验会把候选缩略图发送给评分服务，增加 API 用量；视频目前只核对封面。")
                settings.judge.vision = typer.confirm("已确认评分模型支持图片，启用图片核验？", default=False)
                settings.judge_model.supports_vision = settings.judge.vision
                settings.judge_model.image_transport = "inline"
            typer.echo("\n素材源：NASA / Commons 无需密钥；通用 B-roll 可添加以下来源，留空跳过。")
            for name in ("pexels", "pixabay"):
                key = typer.prompt(name.capitalize() + " API Key", default="", hide_input=True, show_default=False).strip()
                if key:
                    getattr(settings.sources, name).api_key = key
                    settings.sources.enabled.append(name)
        content = _render(settings)
        if config.exists():
            backup = config.with_name(config.name + "." + uuid4().hex[:8] + ".bak")
            _new_private_file(backup, config.read_text(encoding="utf-8"))
            temporary = config.with_name(config.name + "." + uuid4().hex[:8] + ".tmp")
            try:
                _new_private_file(temporary, content)
                os.replace(temporary, config)
            finally:
                temporary.unlink(missing_ok=True)
            typer.echo("原配置已备份：{}".format(backup))
        else:
            _new_private_file(config, content)
        typer.echo("已创建私有配置：{}".format(config))
    try:
        effective = Settings.from_file(str(config))
    except Exception as exc:
        typer.echo("配置无法读取（{}），请检查 TOML 与环境变量格式。".format(type(exc).__name__), err=True)
        raise typer.Exit(1) from None
    server = launch_config(config, output_root)
    client_json = _export(config.parent / "mcp-client.json", json.dumps({"mcpServers": {"scriptmate": server}}, ensure_ascii=False, indent=2) + "\n")
    codex_toml = _export(config.parent / "mcp-codex.toml", "[mcp_servers.scriptmate]\ncommand = {}\nargs = {}\n".format(
        json.dumps(server["command"], ensure_ascii=False), json.dumps(server["args"], ensure_ascii=False)))
    typer.echo("\n接入文件（只有命令与路径，不含密钥）：\n- {}\n- {}".format(client_json, codex_toml))
    launch = [server["command"], *server["args"]]
    typer.echo("\nCodex 可执行：\n" + shell_command(["codex", "mcp", "add", "scriptmate", "--", *launch]))
    typer.echo("\nClaude Code 可执行：\n" + shell_command(["claude", "mcp", "add", "--transport", "stdio", "--scope", "user", "scriptmate", "--", *launch]))
    _show_status(readiness(effective, config.parent))
    typer.echo("\n连接检查：\n" + shell_command(["scriptmate", "check-mcp", "--config", str(config), "--output-root", str(output_root)]))


def setup_mcp(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="Private TOML configuration path."),
    output_root: Path = typer.Option(DEFAULT_OUTPUT, "--output-root", help="Material package root."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Create a blank template and connection files without prompts."),
    search_only: bool = typer.Option(False, "--search-only", help="Configure free source search without model-key prompts."),
    reconfigure: bool = typer.Option(False, "--reconfigure", help="Replace configuration after saving a private backup."),
) -> None:
    """引导配置模型/素材源，生成通用 JSON 与 Codex TOML 接入文件。"""
    try:
        _setup_mcp(config, output_root, non_interactive, search_only, reconfigure)
    except (click.ClickException, click.Abort, typer.Exit):
        raise
    except Exception as exc:
        # Never render Pydantic input values or exception locals containing API keys.
        typer.echo("配置向导失败（{}）；请检查文件权限、配置参数和环境变量。".format(type(exc).__name__), err=True)
        raise typer.Exit(1) from None


async def _check_connection(config: Path, output_root: Path) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    launch = launch_config(config, output_root)
    prefixes = ("PLANNER_MODEL_", "JUDGE_MODEL_", "PREFILTER_MODEL_", "SCRIPTMATE_", "DEEPSEEK_", "OPENAI_", "TYPESAFE_",
                "PEXELS_", "PIXABAY_", "COVERR_", "NASA_IMAGES_", "OPENVERSE_", "COMMONS_", "LIBRARY_",
                "SOURCES__", "MATCHING__", "JUDGE__", "GENERATION__", "OUTPUT__", "CARDS__", "DOWNGRADE__", "CAPCUT__")
    environment = {key: value for key, value in os.environ.items() if key.startswith(prefixes)}
    for key in ("PLANNER_MODEL", "JUDGE_MODEL", "PREFILTER_MODEL"):
        if key in os.environ:
            environment[key] = os.environ[key]
    settings = Settings.from_file(str(config))
    for item in settings.sources.extra:
        if item.api_key_env and item.api_key_env in os.environ:
            environment[item.api_key_env] = os.environ[item.api_key_env]
    parameters = StdioServerParameters(**launch, cwd=str(config.parent), env=environment)
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("doctor", {})
            if result.isError or result.structuredContent is None:
                raise RuntimeError("MCP doctor failed")
            return {"tool_count": len(tools.tools), "doctor": result.structuredContent}


def check_mcp(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="Private TOML configuration path."),
    output_root: Path = typer.Option(DEFAULT_OUTPUT, "--output-root", help="Material package root."),
) -> None:
    """验证配置和真实 stdio 连接，不调用任何模型或素材源 API。"""
    config = config.expanduser().absolute()
    try:
        settings = Settings.from_file(str(config))
    except Exception as exc:
        typer.echo("配置无法读取（{}）。请运行 scriptmate setup-mcp 或检查 TOML 格式。".format(type(exc).__name__), err=True)
        raise typer.Exit(1) from None
    if sys.version_info < (3, 10):
        typer.echo("MCP 需要 Python 3.10+；请用 uv 或新版 Python 安装 [mcp] 依赖。", err=True)
        raise typer.Exit(1)
    try:
        result = asyncio.run(asyncio.wait_for(_check_connection(config, output_root.expanduser().absolute()), timeout=30))
    except ImportError:
        typer.echo("缺少 MCP 依赖；请按 README 安装 [mcp] 版本。", err=True)
        raise typer.Exit(1) from None
    except Exception as exc:
        typer.echo("MCP 连接失败（{}）；检查安装环境、配置路径与服务错误提示。".format(type(exc).__name__), err=True)
        raise typer.Exit(1) from None
    typer.echo("MCP 连接成功：发现 {} 个工具；配置和本机数据可读取。".format(result["tool_count"]))
    _show_status(result["doctor"]["readiness"])
