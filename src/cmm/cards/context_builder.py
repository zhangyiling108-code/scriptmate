from __future__ import annotations

from cmm.models import Segment


def build_card_context(segment: Segment) -> dict:
    return {
        "title": segment.text[:28],
        "body": segment.card_text or segment.text,
        "keywords": " / ".join(segment.keywords_cn or segment.keywords_en),
        "visual_brief": segment.visual_brief,
        "scene_type": segment.scene_type,
    }
