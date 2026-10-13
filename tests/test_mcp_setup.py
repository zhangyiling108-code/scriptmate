import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cmm.cli import app
from cmm.config import Settings


runner = CliRunner()


def test_search_only_setup_creates_private_config_and_real_client_paths(tmp_path):
    target = tmp_path / "with spaces" / "config.toml"
    result = runner.invoke(app, ["setup-mcp", "--config", str(target), "--non-interactive", "--search-only"])
    assert result.exit_code == 0, result.output
    settings = Settings.from_file(str(target))
    assert settings.sources.enabled == ["nasa", "commons"]
    assert settings.planner_model.api_key == ""
    exported = json.loads((target.parent / "mcp-client.json").read_text())
    server = exported["mcpServers"]["scriptmate"]
    assert Path(server["command"]).is_absolute()
    assert server["args"][server["args"].index("--config") + 1] == str(target.absolute())
    assert "ABSOLUTE" not in json.dumps(exported)
    assert (target.parent / "mcp-codex.toml").is_file()
    assert "Codex 可执行" in result.output
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


def test_setup_preserves_existing_config_and_client_edits(tmp_path):
    target = tmp_path / "config.toml"
    original = '[sources]\nenabled=["commons"]\n'
    target.write_text(original)
    client = tmp_path / "mcp-client.json"
    client.write_text('{"user":"custom config"}')
    result = runner.invoke(app, ["setup-mcp", "--config", str(target), "--non-interactive"])
    assert result.exit_code == 0, result.output
    assert target.read_text() == original
    assert client.read_text() == '{"user":"custom config"}'
    assert len(list(tmp_path.glob("mcp-client*.json"))) == 2


def test_setup_does_not_copy_environment_secrets_into_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-private-environment-key")
    monkeypatch.setenv("SOURCES__PEXELS__API_KEY", "synthetic-private-nested-key")
    target = tmp_path / "config.toml"
    result = runner.invoke(app, ["setup-mcp", "--config", str(target), "--non-interactive"])
    assert result.exit_code == 0, result.output
    assert "synthetic-private-environment-key" not in target.read_text()
    assert "synthetic-private-nested-key" not in target.read_text()
    assert "synthetic-private-environment-key" not in result.output


def test_reconfigure_keeps_a_private_backup(tmp_path):
    target = tmp_path / "config.toml"
    original = '[sources]\nenabled=["commons"]\n'
    target.write_text(original)
    result = runner.invoke(app, ["setup-mcp", "--config", str(target), "--non-interactive", "--search-only", "--reconfigure"])
    assert result.exit_code == 0, result.output
    assert Settings.from_file(str(target)).sources.enabled == ["nasa", "commons"]
    backups = list(tmp_path.glob("config.toml.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == original
    if os.name != "nt":
        assert backups[0].stat().st_mode & 0o777 == 0o600


def test_interactive_setup_masks_credentials_and_enables_requested_vision(tmp_path):
    target = tmp_path / "config.toml"
    # Full workflow, DeepSeek, default model, own key, same judge, enable vision, no stock keys.
    answers = "1\n1\n\nsynthetic-private-model-key\ny\ny\n\n\n"
    result = runner.invoke(app, ["setup-mcp", "--config", str(target)], input=answers)
    assert result.exit_code == 0, result.output
    settings = Settings.from_file(str(target))
    assert settings.planner_model.api_key == "synthetic-private-model-key"
    assert settings.judge_model.api_key == "synthetic-private-model-key"
    assert settings.judge.vision is True
    assert settings.judge_model.supports_vision is True
    assert settings.judge.require_visual_evidence is True
    assert "synthetic-private-model-key" not in result.output
    assert "synthetic-private-model-key" not in (tmp_path / "mcp-client.json").read_text()


def test_readiness_explains_missing_keys_and_visual_review():
    from cmm.mcp_setup import readiness
    settings = Settings()
    settings.sources.enabled = ["nasa"]
    status = readiness(settings)
    assert status["search_ready"] is True
    assert status["matching_configured"] is False
    assert status["credentials_verified"] is False
    assert any("planner" in item for item in status["warnings"])
    settings.planner_model.api_key = settings.judge_model.api_key = "synthetic"
    settings.judge.require_visual_evidence = True
    status = readiness(settings)
    assert status["matching_configured"] is True
    assert status["automatic_primary_configured"] is False
    assert any("vision" in item for item in status["warnings"])


def test_readiness_rejects_unusable_inferred_vision():
    from cmm.mcp_setup import readiness
    settings = Settings()
    settings.sources.enabled = ["nasa"]
    settings.planner_model.api_key = settings.judge_model.api_key = "synthetic"
    settings.judge.vision = True
    settings.judge.require_visual_evidence = True
    settings.judge_model.model = "deepseek-v4-flash"
    settings.judge_model.supports_vision = None
    status = readiness(settings)
    assert status["matching_configured"] is False
    assert status["automatic_primary_configured"] is False
    assert any("vision" in item for item in status["warnings"])


def test_generated_windows_commands_are_powershell_safe():
    from cmm.mcp_setup import shell_command
    command = shell_command(["codex", "mcp", "add", "scriptmate", "--", r"C:\R&D\a$b's folder\scriptmate-mcp.exe"], windows=True)
    assert command.startswith("& 'codex'")
    assert r"'C:\R&D\a$b''s folder\scriptmate-mcp.exe'" in command


def test_check_mcp_performs_real_stdio_connection_without_api_calls(tmp_path):
    pytest.importorskip("mcp")
    target = tmp_path / "config.toml"
    target.write_text('[sources]\nenabled=["nasa"]\n')
    result = runner.invoke(app, ["check-mcp", "--config", str(target), "--output-root", str(tmp_path / "jobs")])
    assert result.exit_code == 0, result.output
    assert "6" in result.output
    assert "MCP" in result.output
    assert "未验证" in result.output


def test_check_mcp_forwards_model_environment_without_exporting_it(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    import asyncio
    from cmm.mcp_setup import _check_connection
    target = tmp_path / "config.toml"
    target.write_text('[sources]\nenabled=["nasa"]\n')
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-private-environment-key")
    response = asyncio.run(_check_connection(target, tmp_path / "jobs"))
    assert response["doctor"]["readiness"]["matching_configured"] is True
    assert "synthetic-private-environment-key" not in json.dumps(response)


def test_check_mcp_reports_invalid_config_without_printing_secret(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text('api_key = "synthetic-private-key\n')
    result = runner.invoke(app, ["check-mcp", "--config", str(target)])
    assert result.exit_code != 0
    assert "配置无法读取" in result.output
    assert "synthetic-private-key" not in result.output


def test_invalid_environment_cannot_expose_a_secret_in_setup(tmp_path, monkeypatch):
    import subprocess
    import sys
    monkeypatch.setenv("PREFILTER_MODEL", '{"provider":"typesafe","supports_vision":true,"api_key":"fakekey"}')
    target = tmp_path / "config.toml"
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-m", "cmm.cli", "setup-mcp", "--config", str(target), "--non-interactive"],
                            env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert "fakekey" not in result.stdout + result.stderr
    if target.exists():
        assert "fakekey" not in target.read_text()
