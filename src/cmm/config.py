from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: float = 30.0
    max_retries: int = 1
    # None keeps compatibility with existing configs; explicitly set this for new endpoints.
    supports_vision: Optional[bool] = None
    image_transport: Literal["url", "inline"] = "url"

    @model_validator(mode="before")
    @classmethod
    def _typesafe_defaults(cls, data):
        if isinstance(data, dict) and str(data.get("provider", "")).lower() == "typesafe":
            data = dict(data)
            data.setdefault("model", "jev-latest")
            data.setdefault("base_url", "https://api.typesafe.ai")
            data.setdefault("supports_vision", False)
        return data

    @model_validator(mode="after")
    def _typesafe_capabilities(self):
        if self.provider.lower() == "typesafe" and self.supports_vision:
            raise ValueError("Typesafe System One currently supports metadata judging, not image input.")
        return self


class SourceApiSettings(BaseModel):
    api_key: str = ""
    base_url: str = ""


class OpenSourceSettings(SourceApiSettings):
    allowed_licenses: List[str] = Field(default_factory=lambda: ["cc0", "pdm", "by"])


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
    coverr: SourceApiSettings = SourceApiSettings()
    nasa: SourceApiSettings = SourceApiSettings(base_url="https://images-api.nasa.gov")
    openverse: OpenSourceSettings = OpenSourceSettings(base_url="https://api.openverse.org/v1")
    commons: OpenSourceSettings = OpenSourceSettings(base_url="https://commons.wikimedia.org/w/api.php")
    extra: List[ExternalSourceSettings] = Field(default_factory=list)

    def configured_external_sources(self) -> List[ExternalSourceSettings]:
        return [item for item in self.extra if item.enabled]


class MatchingSettings(BaseModel):
    top_results: int = 3
    search_pool_size: int = 8
    min_score: float = 0.55
    strong_score: float = 0.70
    video_min_resolution: int = 1080
    target_aspect: str = "9:16"
    video_orientation: str = "vertical"
    search_concurrency: int = Field(default=4, ge=1, le=32)
    provider_concurrency: int = Field(default=2, ge=1, le=8)
    search_timeout_seconds: float = Field(default=90.0, gt=0)
    search_cache_ttl_seconds: float = Field(default=86400.0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _backfill_target_aspect(cls, data):
        if not isinstance(data, dict):
            return data
        if "target_aspect" in data:
            return data
        orientation = data.get("video_orientation")
        if orientation == "horizontal":
            data = dict(data)
            data["target_aspect"] = "16:9"
        elif orientation == "square":
            data = dict(data)
            data["target_aspect"] = "1:1"
        elif orientation == "vertical":
            data = dict(data)
            data["target_aspect"] = "9:16"
        return data


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


class CapCutSettings(BaseModel):
    base_url: str = "http://127.0.0.1:8765"


class JudgeSettings(BaseModel):
    vision: bool = False
    require_visual_evidence: bool = False
    prefilter_limit: int = Field(default=12, ge=3, le=100)
    concurrency: int = Field(default=2, ge=1, le=16)
    cache_ttl_seconds: float = Field(default=604800.0, ge=0)


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
    judge_model: ModelSettings = ModelSettings()
    prefilter_model: Optional[ModelSettings] = None
    sources: SourcesSettings = SourcesSettings()
    matching: MatchingSettings = MatchingSettings()
    generation: GenerationSettings = GenerationSettings()
    library: LibrarySettings = LibrarySettings()
    cards: CardSettings = CardSettings()
    output: OutputSettings = OutputSettings()
    capcut: CapCutSettings = CapCutSettings()
    judge: JudgeSettings = JudgeSettings()
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
                    "model": ["PLANNER_MODEL_NAME", "PLANNER_MODEL"],
                    "api_key": ["PLANNER_MODEL_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"],
                    "base_url": ["PLANNER_MODEL_BASE_URL", "DEEPSEEK_BASE_URL", "OPENAI_BASE_URL"],
                    "timeout_seconds": "PLANNER_MODEL_TIMEOUT_SECONDS",
                    "max_retries": "PLANNER_MODEL_MAX_RETRIES",
                },
            ),
            "judge_model": _load_judge_model(data.get("judge_model", legacy_llm)),
            "prefilter_model": _load_prefilter_model(data.get("prefilter_model")),
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
                "coverr": _merge_env_overrides(
                    data.get("sources", {}).get("coverr", legacy_stock.get("coverr", {})),
                    {"api_key": "COVERR_API_KEY", "base_url": "COVERR_BASE_URL"},
                ),
                "nasa": _merge_env_overrides(
                    data.get("sources", {}).get("nasa", legacy_stock.get("nasa", {})),
                    {"api_key": "NASA_IMAGES_API_KEY", "base_url": "NASA_IMAGES_BASE_URL"},
                ),
                "openverse": _merge_env_overrides(
                    data.get("sources", {}).get("openverse", {}),
                    {"api_key": "OPENVERSE_API_TOKEN", "base_url": "OPENVERSE_BASE_URL"},
                ),
                "commons": _merge_env_overrides(
                    data.get("sources", {}).get("commons", {}),
                    {"base_url": "COMMONS_BASE_URL"},
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
            "capcut": _merge_env_overrides(
                data.get("capcut", {}),
                {
                    "base_url": "CAPCUT_MATE_BASE_URL",
                },
            ),
            "judge": _merge_env_overrides(
                data.get("judge", {}),
                {
                    "vision": "SCRIPTMATE_JUDGE_VISION",
                    "require_visual_evidence": "SCRIPTMATE_REQUIRE_VISUAL_EVIDENCE",
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
    return tomllib.loads(path.read_text(encoding="utf-8-sig"))


def _load_judge_model(payload):
    import os

    provider = os.getenv("JUDGE_MODEL_PROVIDER") or payload.get("provider", "deepseek")
    typesafe = provider.lower() == "typesafe"
    return _merge_env_overrides(payload, {
        "provider": "JUDGE_MODEL_PROVIDER",
        "model": ["JUDGE_MODEL_NAME", "JUDGE_MODEL"] + (["TYPESAFE_DEFAULT_MODEL"] if typesafe else []),
        # Never send another provider's fallback key to Typesafe.
        "api_key": ["JUDGE_MODEL_API_KEY"] + (["TYPESAFE_API_KEY"] if typesafe else ["DEEPSEEK_API_KEY", "OPENAI_API_KEY"]),
        "base_url": ["JUDGE_MODEL_BASE_URL"] + (["TYPESAFE_BASE_URL"] if typesafe else ["DEEPSEEK_BASE_URL", "OPENAI_BASE_URL"]),
        "timeout_seconds": "JUDGE_MODEL_TIMEOUT_SECONDS",
        "max_retries": "JUDGE_MODEL_MAX_RETRIES",
        "supports_vision": "JUDGE_MODEL_SUPPORTS_VISION",
        "image_transport": "JUDGE_MODEL_IMAGE_TRANSPORT",
    })


def _load_prefilter_model(payload):
    import os

    if payload is None and not os.getenv("PREFILTER_MODEL_PROVIDER"):
        return None
    payload = payload or {}
    provider = os.getenv("PREFILTER_MODEL_PROVIDER") or payload.get("provider", "typesafe")
    typesafe = provider.lower() == "typesafe"
    return _merge_env_overrides({"provider": provider, **payload}, {
        "provider": "PREFILTER_MODEL_PROVIDER",
        "model": ["PREFILTER_MODEL_NAME"] + (["TYPESAFE_DEFAULT_MODEL"] if typesafe else []),
        "api_key": ["PREFILTER_MODEL_API_KEY"] + (["TYPESAFE_API_KEY"] if typesafe else []),
        "base_url": ["PREFILTER_MODEL_BASE_URL"] + (["TYPESAFE_BASE_URL"] if typesafe else []),
        "timeout_seconds": "PREFILTER_MODEL_TIMEOUT_SECONDS",
        "max_retries": "PREFILTER_MODEL_MAX_RETRIES",
    })


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
