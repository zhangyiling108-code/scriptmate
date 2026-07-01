from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from cmm.library.metadata_loader import load_metadata, normalize_tags
from cmm.models import LibraryAsset, LibraryScanResult, model_dump_compat
from cmm.utils.files import write_json
from cmm.utils.media import probe_video


SUPPORTED_SUFFIXES = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".webp"}


def scan_library(
    root: str,
    metadata_path: str = "",
    output_path: str = "",
    cache_path: str = "",
) -> LibraryScanResult:
    root_path = Path(root).expanduser().resolve()
    metadata = load_metadata(metadata_path) if metadata_path else {}
    cached_assets = _load_cached_assets(cache_path or output_path, root_path)
    assets: List[LibraryAsset] = []

    for file_path in sorted(root_path.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        rel_path = file_path.relative_to(root_path).as_posix()
        fingerprint = _fingerprint(file_path)
        cached = cached_assets.get(rel_path)
        if cached and cached.fingerprint == fingerprint:
            assets.append(_merge_metadata(cached, metadata.get(rel_path, {}), file_path, rel_path))
            continue
        assets.append(_build_asset(file_path, root_path, metadata.get(rel_path, {}), fingerprint))

    result = LibraryScanResult(root=str(root_path), assets=assets, output_path=output_path or None)
    if output_path:
        write_json(output_path, model_dump_compat(result))
    return result


def default_index_path(root: str) -> str:
    return str(Path(root).expanduser().resolve() / ".scriptmate-library-index.json")


def _load_cached_assets(path: str, root_path: Path) -> Dict[str, LibraryAsset]:
    if not path:
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    try:
        payload = __import__("json").loads(target.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if str(payload.get("root", "")) != str(root_path):
        return {}
    loaded = {}
    for item in payload.get("assets", []):
        try:
            asset = LibraryAsset(**item)
        except Exception:
            continue
        rel_path = asset.relative_path or _relative_to_root(asset.path, root_path)
        if rel_path:
            loaded[rel_path] = asset
    return loaded


def _build_asset(file_path: Path, root_path: Path, item: Dict[str, object], fingerprint: str) -> LibraryAsset:
    stat = file_path.stat()
    rel_path = file_path.relative_to(root_path).as_posix()
    mime, _ = mimetypes.guess_type(str(file_path))
    asset_type = "video" if mime and mime.startswith("video") else "image"
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    warnings: List[str] = []

    if asset_type == "image":
        try:
            with Image.open(file_path) as image:
                width, height = image.size
        except Exception as exc:
            warnings.append("image_probe_failed: {0}".format(exc))
    else:
        try:
            probed = probe_video(str(file_path))
            width = probed.width
            height = probed.height
            duration = probed.duration
            if width is None or height is None:
                warnings.append("video_probe_incomplete")
        except Exception as exc:
            warnings.append("video_probe_failed: {0}".format(exc))

    title = str(item.get("title", "") or _title_from_path(file_path))
    description = str(item.get("description", "") or "")
    tags = normalize_tags(item.get("tags", []))
    category = str(item.get("category", "") or file_path.parent.name or "library")
    aspect_ratio = _aspect_ratio(width, height)
    orientation = _orientation(width, height)
    searchable_text = _searchable_text(file_path, title, description, tags, category)
    metadata_complete = bool(title and (description or tags or category))

    return LibraryAsset(
        path=str(file_path),
        relative_path=rel_path,
        title=title,
        description=description,
        tags=tags,
        category=category,
        asset_type=asset_type,
        duration=duration,
        width=width,
        height=height,
        file_size=stat.st_size,
        mtime=stat.st_mtime,
        aspect_ratio=aspect_ratio,
        orientation=orientation,
        searchable_text=searchable_text,
        fingerprint=fingerprint,
        metadata_complete=metadata_complete,
        warnings=warnings,
    )


def _merge_metadata(asset: LibraryAsset, item: Dict[str, object], file_path: Path, rel_path: str) -> LibraryAsset:
    title = str(item.get("title", "") or _title_from_path(file_path))
    description = str(item.get("description", "") or "")
    tags = normalize_tags(item.get("tags", []))
    category = str(item.get("category", "") or file_path.parent.name or "library")
    return asset.model_copy(
        update={
            "path": str(file_path),
            "relative_path": rel_path,
            "title": title,
            "description": description,
            "tags": tags,
            "category": category,
            "searchable_text": _searchable_text(file_path, title, description, tags, category),
            "metadata_complete": bool(title and (description or tags or category)),
        }
    )


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    return "{0}:{1}:{2}".format(path.as_posix(), stat.st_size, int(stat.st_mtime))


def _title_from_path(path: Path) -> str:
    words = re.sub(r"[_-]+", " ", path.stem).strip()
    return words or path.stem


def _searchable_text(path: Path, title: str, description: str, tags: List[str], category: str) -> str:
    parts = [title, description, " ".join(tags), category, path.stem, path.parent.name]
    return " ".join(part for part in parts if part).lower()


def _aspect_ratio(width: Optional[int], height: Optional[int]) -> str:
    if not width or not height:
        return ""
    ratio = width / height
    known = {
        "9:16": 9 / 16,
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "3:4": 3 / 4,
        "1:1": 1.0,
    }
    return min(known, key=lambda key: abs(known[key] - ratio))


def _orientation(width: Optional[int], height: Optional[int]) -> str:
    if not width or not height:
        return ""
    if width == height:
        return "square"
    return "vertical" if height > width else "horizontal"


def _relative_to_root(path: str, root_path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root_path).as_posix()
    except Exception:
        return ""
