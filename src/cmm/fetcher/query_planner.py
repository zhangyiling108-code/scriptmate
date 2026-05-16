from __future__ import annotations

import re
from typing import Dict, List

from cmm.models import Segment, ShotPlan


DOMAIN_RULES = [
    {
        "name": "manufacturing",
        "hints": ("factory", "production", "manufacturing", "assembly", "工厂", "生产", "制造"),
        "queries": [
            "factory assembly line",
            "industrial robot assembly line",
            "automotive manufacturing",
        ],
        "pexels": ["factory worker assembly line", "industrial robot factory"],
        "pixabay": ["factory, assembly, industry", "robot, manufacturing, technology"],
    },
    {
        "name": "logistics",
        "hints": ("port", "shipping", "export", "logistics", "cargo", "港口", "装船", "出口", "物流"),
        "queries": [
            "container port logistics",
            "cargo ship loading port",
            "vehicle export terminal",
        ],
        "pexels": ["aerial shipping port cranes", "cars at shipping port"],
        "pixabay": ["container, port, logistics", "cargo ship, export, loading"],
    },
    {
        "name": "technology",
        "hints": ("ai", "chip", "server", "technology", "battery", "ev", "electric vehicle", "人工智能", "芯片", "电池", "新能源汽车"),
        "queries": [
            "data center server racks",
            "technology manufacturing",
            "electric vehicle battery production",
        ],
        "pexels": ["server room technology", "electric car charging station"],
        "pixabay": ["technology, server, data", "battery, electric, factory"],
    },
    {
        "name": "finance",
        "hints": ("economy", "market", "gdp", "inflation", "consumer", "经济", "市场", "消费", "投资"),
        "queries": [
            "business district skyline",
            "stock market trading screen",
            "consumer spending shopping mall",
        ],
        "pexels": ["business district skyline", "stock market screen"],
        "pixabay": ["business, economy, market", "finance, chart, trading"],
    },
    {
        "name": "medical",
        "hints": ("medical", "health", "doctor", "hospital", "metabolism", "医疗", "健康", "医院", "代谢"),
        "queries": [
            "doctor hospital consultation",
            "medical science microscope",
            "human body anatomy illustration",
        ],
        "pexels": ["doctor hospital patient", "medical laboratory microscope"],
        "pixabay": ["medical, hospital, doctor", "microscope, science, health"],
    },
    {
        "name": "agriculture",
        "hints": ("agriculture", "crop", "farm", "greenhouse", "农业", "作物", "农田"),
        "queries": [
            "greenhouse agriculture",
            "crop field irrigation",
            "modern farm machinery",
        ],
        "pexels": ["greenhouse agriculture workers", "crop field irrigation"],
        "pixabay": ["agriculture, farm, crops", "greenhouse, plants, irrigation"],
    },
]

GENERAL_AVOID_TERMS = [
    "temple",
    "pagoda",
    "buddhist",
    "wedding",
    "cartoon",
    "toy",
    "cotton candy",
    "sad child",
    "vintage ship",
    "titanic",
]


def enrich_segment_plan(segment: Segment) -> None:
    blob = _segment_blob(segment)
    matched_rules = [rule for rule in DOMAIN_RULES if any(hint in blob for hint in rule["hints"])]
    if not matched_rules:
        matched_rules = []

    extra_queries: List[str] = []
    provider_queries: Dict[str, List[str]] = {"pexels": [], "pixabay": []}
    for rule in matched_rules:
        extra_queries.extend(rule["queries"])
        provider_queries["pexels"].extend(rule["pexels"])
        provider_queries["pixabay"].extend(rule["pixabay"])

    segment.search_queries = _dedupe([*segment.search_queries, *extra_queries])
    segment.provider_queries = _merge_provider_queries(segment.provider_queries, provider_queries)
    segment.avoid_terms = _dedupe([*segment.avoid_terms, *GENERAL_AVOID_TERMS])

    if not segment.shots:
        segment.shots = _infer_shots(segment, matched_rules)
    else:
        segment.shots = [_normalize_shot(shot, segment.avoid_terms) for shot in segment.shots]


def provider_queries_for(segment: Segment, provider: str) -> List[str]:
    provider_specific = list(segment.provider_queries.get(provider, []))
    for shot in segment.shots:
        provider_specific.extend(shot.provider_queries.get(provider, []))
    return _dedupe(provider_specific)


def all_shot_queries(segment: Segment) -> List[str]:
    queries: List[str] = []
    for shot in segment.shots:
        queries.extend(shot.queries)
    return _dedupe(queries)


def candidate_bucket(score: float) -> str:
    if score >= 0.65:
        return "ready"
    if score >= 0.45:
        return "review"
    if score >= 0.25:
        return "weak_reference"
    return "rejected"


def candidate_matches_avoid_terms(segment: Segment, evidence: str) -> bool:
    lowered = evidence.lower()
    return any(term.lower() in lowered for term in segment.avoid_terms if term)


def visual_caption_for_candidate(fields: List[str]) -> str:
    tokens = []
    for field in fields:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(field).lower()):
            if token in {"video", "photo", "image", "pexels", "pixabay", "https", "www"}:
                continue
            tokens.append(token.replace("-", " "))
    return ", ".join(_dedupe(tokens)[:18])


def _infer_shots(segment: Segment, rules: List[dict]) -> List[ShotPlan]:
    blob = _segment_blob(segment)
    shots: List[ShotPlan] = []
    if any(hint in blob for hint in ("factory", "production", "工厂", "生产")):
        shots.append(ShotPlan(intent="factory production", queries=["factory assembly line", "automotive manufacturing"]))
    if any(hint in blob for hint in ("port", "ship", "export", "港口", "装船", "出口")):
        shots.append(ShotPlan(intent="shipping logistics", queries=["cars at shipping port", "container port logistics"]))
    if any(hint in blob for hint in ("global", "market", "全球", "市场")):
        shots.append(ShotPlan(intent="global market", queries=["global logistics network", "world map trade routes"]))
    if not shots and rules:
        first = rules[0]
        shots.append(ShotPlan(intent="{0} visual".format(first["name"]), queries=list(first["queries"][:2])))
    return [_normalize_shot(shot, segment.avoid_terms) for shot in shots]


def _normalize_shot(shot: ShotPlan, avoid_terms: List[str]) -> ShotPlan:
    shot.queries = _dedupe([query for query in shot.queries if not _contains_cjk(query)])
    shot.provider_queries = {
        provider: _dedupe([query for query in queries if not _contains_cjk(query)])
        for provider, queries in shot.provider_queries.items()
    }
    shot.avoid_terms = _dedupe([*shot.avoid_terms, *avoid_terms])
    return shot


def _merge_provider_queries(base: Dict[str, List[str]], extra: Dict[str, List[str]]) -> Dict[str, List[str]]:
    merged = {key: list(value) for key, value in base.items()}
    for provider, queries in extra.items():
        merged[provider] = _dedupe([*merged.get(provider, []), *queries])
    return merged


def _segment_blob(segment: Segment) -> str:
    return " ".join(
        [
            segment.text,
            segment.visual_brief,
            segment.narrative_subject,
            segment.context_statement,
            " ".join(segment.context_tags),
            " ".join(segment.keywords_cn),
            " ".join(segment.keywords_en),
            " ".join(segment.search_queries),
        ]
    ).lower()


def _dedupe(items: List[str]) -> List[str]:
    result = []
    seen = set()
    for item in items:
        normalized = " ".join(str(item).split()).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
    return result


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value or ""))
