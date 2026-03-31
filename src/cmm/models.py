from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SegmentRole = Literal["hook", "claim", "explanation", "example", "data_point", "summary"]
VisualType = Literal["stock_video", "stock_image", "data_card", "text_card", "skip"]
SceneType = Literal["talking_head", "b_roll", "infographic", "text_card"]
MediaType = Literal["video", "image"]
MatchLevel = Literal["exact", "approx", "generic"]
SourceType = str


class Segment(BaseModel):
    id: int
    text: str
    segment_role: SegmentRole = "explanation"
    visual_type: VisualType = "stock_video"
    scene_type: SceneType = "b_roll"
    duration_hint: float = 3.0
    narrative_subject: str = ""
    context_statement: str = ""
    context_tags: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list)
    search_query_layers: Dict[str, List[str]] = Field(default_factory=dict)
    keywords_cn: List[str] = Field(default_factory=list)
    keywords_en: List[str] = Field(default_factory=list)
    card_text: str = ""
    visual_brief: str = ""


class AnalysisResult(BaseModel):
    segments: List[Segment]
    overall_style: str = "clean documentary"
    target_aspect: str = "9:16"


class LibraryAsset(BaseModel):
    path: str
    title: str = ""
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    category: str = ""
    asset_type: MediaType
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


class MaterialCandidate(BaseModel):
    id: str
    source_type: SourceType
    media_type: MediaType
    uri: str
    thumbnail_url: str = ""
    preview_uri: str = ""
    source_page: str = ""
    relevance_score: float = 0.0
    match_level: MatchLevel = "generic"
    reason: str = ""
    license_type: str = ""
    attribution_required: bool = False
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    quality_signals: Dict[str, Any] = Field(default_factory=dict)
    provider_meta: Dict[str, Any] = Field(default_factory=dict)


class SegmentMatch(BaseModel):
    segment: Segment
    chosen: Optional[MaterialCandidate] = None
    alternatives: List[MaterialCandidate] = Field(default_factory=list)
    external_search_links: List[Dict[str, str]] = Field(default_factory=list)
    fallback_used: bool = False
    action: str = "matched"
    notes: List[str] = Field(default_factory=list)


class MatchedSegment(BaseModel):
    segment: Segment
    primary: Optional[MaterialCandidate] = None
    candidates: List[MaterialCandidate] = Field(default_factory=list)
    selection_reason: str = ""
    fallback_used: bool = False


class MatchSummary(BaseModel):
    exact: int = 0
    approximate: int = 0
    generic_real: int = 0
    generated: int = 0
    skipped: int = 0


class MatchInput(BaseModel):
    text: str
    aspect: str = "9:16"
    resolution: str = "1080"
    style: str = "clean"
    top_results: int = 3
    output_dir: str
    save_candidates: bool = True
    analysis_only: bool = False


class MatchResult(BaseModel):
    script_file: str = ""
    created_at: str
    total_segments: int
    analysis: AnalysisResult
    segments: List[SegmentMatch]
    match_summary: MatchSummary
    output_dir: str
    downloads: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    cache_hits: Dict[str, int] = Field(default_factory=dict)


class SearchResult(BaseModel):
    query: str
    source: str
    candidates: List[MaterialCandidate] = Field(default_factory=list)


class DraftResult(BaseModel):
    success: bool
    draft_dir: Optional[str] = None
    manifest_path: Optional[str] = None
    message: str = ""


class RenderResult(BaseModel):
    success: bool
    output_path: Optional[str] = None
    message: str = ""


class VideoSource(BaseModel):
    path: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    has_audio: Optional[bool] = None


class LibraryScanResult(BaseModel):
    root: str
    assets: List[LibraryAsset]
    output_path: Optional[str] = None


def model_dump_compat(model: Any) -> Dict[str, Any]:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def ensure_path(value: str) -> str:
    return str(Path(value).expanduser())
