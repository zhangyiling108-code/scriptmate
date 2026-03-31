from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import List

from cmm.library.metadata_loader import load_metadata, normalize_tags
from cmm.models import LibraryAsset, LibraryScanResult, model_dump_compat
from cmm.utils.files import write_json


SUPPORTED_SUFFIXES = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".webp"}


def scan_library(root: str, metadata_path: str = "", output_path: str = "") -> LibraryScanResult:
    root_path = Path(root).expanduser()
    metadata = load_metadata(metadata_path) if metadata_path else {}
    assets: List[LibraryAsset] = []
    for file_path in sorted(root_path.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        rel_path = str(file_path.relative_to(root_path))
        item = metadata.get(rel_path, {})
        mime, _ = mimetypes.guess_type(str(file_path))
        asset_type = "video" if mime and mime.startswith("video") else "image"
        assets.append(
            LibraryAsset(
                path=str(file_path),
                title=str(item.get("title", file_path.stem)),
                description=str(item.get("description", "")),
                tags=normalize_tags(item.get("tags", [])),
                category=str(item.get("category", file_path.parent.name)),
                asset_type=asset_type,
            )
        )
    result = LibraryScanResult(root=str(root_path), assets=assets, output_path=output_path or None)
    if output_path:
        write_json(output_path, model_dump_compat(result))
    return result
