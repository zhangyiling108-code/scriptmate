from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
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

    def load_json(self, namespace: str, key: str, max_age_seconds: Optional[float] = None) -> Optional[Any]:
        path = self.path_for(namespace, key)
        try:
            if max_age_seconds is not None and time.time() - path.stat().st_mtime > max_age_seconds:
                return None
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def save_json(self, namespace: str, key: str, payload: Any) -> Path:
        path = self.path_for(namespace, key)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
                temp_path = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return path

    def has(self, namespace: str, key: str) -> bool:
        return self.path_for(namespace, key).exists()
