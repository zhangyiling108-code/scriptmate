from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4.1-mini"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 30.0
    max_retries: int = 1


class SourceApiSettings(BaseModel):
    api_key: str = ""
    base_url: str = ""


class ExternalSourceSettings(BaseModel):
    name: str
    enabled: bool = False
    kind: str = "manual"
    license: str = "paid"
    priority: int = 100
    home_url: str = ""
    search_url_template: str = ""
    api_key: str = ""
    api_key_env: str = ""
    base_url: str = ""
    notes: str = ""


class SourcesSettings(BaseModel):
    enabled: List[str] = Field(default_factory=lambda: ["pexels", "pixabay"])
    pexels: SourceApiSettings = SourceApiSettings()
    pixabay: SourceApiSettings = SourceApiSettings()
    extra: List[ExternalSourceSettings] = Field(default_factory=list)

    def configured_external_sources(self) -> List[ExternalSourceSettings]:
        return [item for item in self.extra if item.enabled]


class MatchingSettings(BaseModel):
    top_results: int = 3
    search_pool_size: int = 8
    min_score: float = 0.55
    strong_score: float = 0.70
    video_min_resolution: int = 1080
    video_orientation: str = "vertical"


class GenerationSettings(BaseModel):
    charts: bool = True
    ai_images: bool = False
    chart_style: str = "dark_professional"


class LibrarySettings(BaseModel):
    root: str = ""
    metadata: str = ""


class CardSettings(BaseModel):
    width: int = 1080
    height: int = 1920
    theme: str = "clean"


class OutputSettings(BaseModel):
    format: str = "both"
    download_quality: str = "hd"
    cache_dir: str = ""


class DowngradeSettings(BaseModel):
    planner_fallback: bool = False
    judge_fallback: bool = False
    search_fallback: bool = False
    generated_fallback: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
        extra="ignore",
    )

    planner_model: ModelSettings = ModelSettings()
    judge_model: ModelSettings = ModelSettings(model="gpt-4o-mini")
    sources: SourcesSettings = SourcesSettings()
    matching: MatchingSettings = MatchingSettings()
    generation: GenerationSettings = GenerationSettings()
    library: LibrarySettings = LibrarySettings()
    cards: CardSettings = CardSettings()
    output: OutputSettings = OutputSettings()
    downgrade: DowngradeSettings = DowngradeSettings()

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> "Settings":
        data = {}
        if path:
            data = _load_toml(Path(path))
        elif Path("config.toml").exists():
            data = _load_toml(Path("config.toml"))

        legacy_llm = data.get("llm", {})
        legacy_stock = data.get("stock", {})
        mapping = {
            "planner_model": _merge_env_overrides(
                data.get("planner_model", legacy_llm),
                {
                    "provider": "PLANNER_MODEL_PROVIDER",
                    "model": "PLANNER_MODEL_NAME",
                    "api_key": ["PLANNER_MODEL_API_KEY", "OPENAI_API_KEY"],
                    "base_url": ["PLANNER_MODEL_BASE_URL", "OPENAI_BASE_URL"],
                    "timeout_seconds": "PLANNER_MODEL_TIMEOUT_SECONDS",
                    "max_retries": "PLANNER_MODEL_MAX_RETRIES",
                },
            ),
            "judge_model": _merge_env_overrides(
                data.get("judge_model", legacy_llm),
                {
                    "provider": "JUDGE_MODEL_PROVIDER",
                    "model": "JUDGE_MODEL_NAME",
                    "api_key": ["JUDGE_MODEL_API_KEY", "OPENAI_API_KEY"],
                    "base_url": ["JUDGE_MODEL_BASE_URL", "OPENAI_BASE_URL"],
                    "timeout_seconds": "JUDGE_MODEL_TIMEOUT_SECONDS",
                    "max_retries": "JUDGE_MODEL_MAX_RETRIES",
                },
            ),
            "sources": {
                "enabled": data.get("sources", {}).get("enabled", ["pexels", "pixabay"]),
                "pexels": _merge_env_overrides(
                    data.get("sources", {}).get("pexels", legacy_stock.get("pexels", {})),
                    {"api_key": "PEXELS_API_KEY", "base_url": "PEXELS_BASE_URL"},
                ),
                "pixabay": _merge_env_overrides(
                    data.get("sources", {}).get("pixabay", legacy_stock.get("pixabay", {})),
                    {"api_key": "PIXABAY_API_KEY", "base_url": "PIXABAY_BASE_URL"},
                ),
                "extra": _load_external_sources(data.get("sources", {}).get("extra", [])),
            },
            "matching": data.get("matching", {}),
            "generation": data.get("generation", {}),
            "library": _merge_env_overrides(
                data.get("library", {}),
                {
                    "root": "LIBRARY_ROOT",
                    "metadata": "LIBRARY_METADATA",
                },
            ),
            "cards": data.get("cards", {}),
            "output": _merge_env_overrides(
                data.get("output", {}),
                {
                    "cache_dir": "SCRIPTMATE_CACHE_DIR",
                },
            ),
            "downgrade": _merge_env_overrides(
                data.get("downgrade", {}),
                {
                    "planner_fallback": "SCRIPTMATE_ALLOW_PLANNER_FALLBACK",
                    "judge_fallback": "SCRIPTMATE_ALLOW_JUDGE_FALLBACK",
                    "search_fallback": "SCRIPTMATE_ALLOW_SEARCH_FALLBACK",
                    "generated_fallback": "SCRIPTMATE_ALLOW_GENERATED_FALLBACK",
                },
            ),
        }
        return cls(**mapping)


def _load_toml(path: Path):
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _merge_env_overrides(payload, env_map):
    import os

    result = dict(payload)
    for key, env_name in env_map.items():
        if isinstance(env_name, (list, tuple)):
            value = next((os.getenv(item) for item in env_name if os.getenv(item) not in (None, "")), None)
        else:
            value = os.getenv(env_name)
        if value not in (None, ""):
            if isinstance(result.get(key), bool) or str(result.get(key)).lower() in {"true", "false"}:
                result[key] = str(value).lower() in {"1", "true", "yes", "on"}
            else:
                result[key] = value
    return result


def _load_external_sources(items):
    import os

    loaded = []
    for raw in items or []:
        payload = dict(raw)
        env_name = payload.get("api_key_env")
        if env_name and os.getenv(env_name):
            payload["api_key"] = os.getenv(env_name, "")
        loaded.append(payload)
    return loaded
