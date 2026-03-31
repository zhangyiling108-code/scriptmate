from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from cmm.models import MaterialCandidate, Segment


class FallbackManager:
    def __init__(self, mapping_path: str, generic_dir: str):
        self.mapping = self._load_mapping(mapping_path)
        self.generic_dir = Path(generic_dir)

    def mapped_queries(self, segment: Segment) -> List[str]:
        queries: List[str] = []
        for keyword in segment.keywords_cn:
            if keyword in self.mapping:
                queries.extend(self.mapping[keyword].get("queries", []))
        return queries

    def generic_candidates(self, segment: Segment, top_k: int = 3) -> List[MaterialCandidate]:
        category = self._category_for_segment(segment)
        folder = self.generic_dir / category
        if not folder.exists():
            return []
        results = []
        for item in sorted(folder.iterdir())[:top_k]:
            if not item.is_file():
                continue
            results.append(
                MaterialCandidate(
                    id="generic:{0}".format(item.name),
                    source_type="generic",
                    media_type="video" if item.suffix.lower() in {".mp4", ".mov", ".m4v"} else "image",
                    uri=str(item),
                    thumbnail_url=str(item),
                    preview_uri=str(item),
                    source_page=str(item),
                    relevance_score=0.35,
                    match_level="generic",
                    license_type="generic-library",
                    attribution_required=False,
                    tags=[category],
                    quality_signals={"fallback": True},
                    provider_meta={"category": category},
                )
            )
        return results

    def _category_for_segment(self, segment: Segment) -> str:
        for keyword in segment.keywords_cn:
            if keyword in self.mapping:
                return self.mapping[keyword].get("fallback_category", "technology")
        return "technology"

    def _load_mapping(self, path: str) -> Dict[str, Dict[str, object]]:
        target = Path(path)
        if not target.exists():
            return {}
        return json.loads(target.read_text(encoding="utf-8"))
