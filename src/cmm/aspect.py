from __future__ import annotations

from typing import Tuple


SUPPORTED_ASPECTS = {
    "9:16": (9, 16),
    "16:9": (16, 9),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "1:1": (1, 1),
}


def normalize_aspect(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("*", ":").replace("x", ":")
    normalized = normalized.replace(" ", "")
    if normalized not in SUPPORTED_ASPECTS:
        raise ValueError(
            "Unsupported aspect ratio: {0}. Supported values: {1}".format(
                value,
                ", ".join(SUPPORTED_ASPECTS),
            )
        )
    return normalized


def aspect_dimensions(aspect: str) -> Tuple[int, int]:
    return SUPPORTED_ASPECTS[normalize_aspect(aspect)]


def orientation_for_aspect(aspect: str) -> str:
    width, height = aspect_dimensions(aspect)
    if width > height:
        return "horizontal"
    if height > width:
        return "vertical"
    return "square"


def aspect_matches(width: int, height: int, target_aspect: str, tolerance: float = 0.08) -> bool:
    if width <= 0 or height <= 0:
        return True
    target_width, target_height = aspect_dimensions(target_aspect)
    actual_ratio = width / height
    target_ratio = target_width / target_height
    return abs(actual_ratio - target_ratio) / target_ratio <= tolerance


def aspect_fit(width: int, height: int, target_aspect: str) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    target_width, target_height = aspect_dimensions(target_aspect)
    actual_ratio = width / height
    target_ratio = target_width / target_height
    delta = abs(actual_ratio - target_ratio) / target_ratio
    return max(0.0, min(1.0, 1.0 - (delta / 0.25)))
