from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional


class FileCache:
    def __init__(self, root: str):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, namespace: str, key: str, suffix: str = ".json") -> Path:
        namespace_dir = self.root / namespace
        namespace_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return namespace_dir / "{0}{1}".format(digest, suffix)

    def load_json(self, namespace: str, key: str) -> Optional[Any]:
        path = self.path_for(namespace, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_json(self, namespace: str, key: str, payload: Any) -> Path:
        path = self.path_for(namespace, key)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def has(self, namespace: str, key: str) -> bool:
        return self.path_for(namespace, key).exists()
