from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List


def load_metadata(path: str) -> Dict[str, Dict[str, object]]:
    target = Path(path)
    if not target.exists():
        return {}
    if target.suffix.lower() == ".jsonl":
        records = {}
        for line in target.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            records[item["path"]] = item
        return records

    with target.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        records = {}
        for row in reader:
            row["tags"] = [part.strip() for part in (row.get("tags") or "").split("|") if part.strip()]
            records[row["path"]] = row
        return records


def normalize_tags(value) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split("|") if part.strip()]
    return []
