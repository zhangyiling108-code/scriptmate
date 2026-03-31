from pathlib import Path

from cmm.config import Settings


def test_settings_load_new_and_legacy_keys(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[planner_model]
provider = "openai"
model = "planner-x"
api_key = "x"
base_url = "https://example.com/v1"

[judge_model]
provider = "openai"
model = "judge-x"
api_key = "x"
base_url = "https://example.com/v1"

[sources.pexels]
api_key = "pexels-key"

[sources.pixabay]
api_key = "pixabay-key"

[matching]
search_pool_size = 10
""".strip(),
        encoding="utf-8",
    )
    settings = Settings.from_file(str(config_path))
    assert settings.planner_model.model == "planner-x"
    assert settings.judge_model.model == "judge-x"
    assert settings.sources.pexels.api_key == "pexels-key"
    assert settings.sources.pixabay.api_key == "pixabay-key"
    assert settings.matching.search_pool_size == 10


def test_settings_accept_openai_env_fallback(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[planner_model]
provider = "openai"
model = "gpt-4o-mini"

[judge_model]
provider = "openai"
model = "gpt-4o-mini"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    settings = Settings.from_file(str(config_path))
    assert settings.planner_model.api_key == "openai-test-key"
    assert settings.judge_model.api_key == "openai-test-key"
    assert settings.planner_model.base_url == "https://api.openai.com/v1"
    assert settings.judge_model.base_url == "https://api.openai.com/v1"


def test_settings_read_downgrade_flags_from_env(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("SCRIPTMATE_ALLOW_PLANNER_FALLBACK", "true")
    monkeypatch.setenv("SCRIPTMATE_ALLOW_JUDGE_FALLBACK", "1")
    monkeypatch.setenv("SCRIPTMATE_ALLOW_SEARCH_FALLBACK", "yes")
    monkeypatch.setenv("SCRIPTMATE_ALLOW_GENERATED_FALLBACK", "on")

    settings = Settings.from_file(str(config_path))

    assert settings.downgrade.planner_fallback is True
    assert settings.downgrade.judge_fallback is True
    assert settings.downgrade.search_fallback is True
    assert settings.downgrade.generated_fallback is True


def test_settings_load_external_paid_sources_and_api_key_from_env(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[sources]
enabled = ["pexels", "pixabay"]

[[sources.extra]]
name = "pond5"
enabled = true
kind = "manual"
license = "paid"
priority = 20
home_url = "https://www.pond5.com/"
search_url_template = "https://www.pond5.com/search?kw={query}"
api_key_env = "POND5_API_KEY"
notes = "Preferred for cinematic b-roll"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("POND5_API_KEY", "pond5-secret")

    settings = Settings.from_file(str(config_path))

    assert len(settings.sources.extra) == 1
    extra = settings.sources.extra[0]
    assert extra.name == "pond5"
    assert extra.enabled is True
    assert extra.api_key == "pond5-secret"
    assert settings.sources.configured_external_sources()[0].name == "pond5"
