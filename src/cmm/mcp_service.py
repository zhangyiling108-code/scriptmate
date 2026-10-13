"""Agent-independent operations shared by the local MCP adapter."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Dict, Optional
from uuid import uuid4
from urllib.parse import quote, quote_plus

from cmm.aspect import normalize_aspect
from cmm.cache import FileCache
from cmm.config import Settings
from cmm.models import MatchInput, model_dump_compat
from cmm.paths import data_directory
from cmm.pipeline import analyze_script, match_script, search_single_query


class ScriptMateService:
    def __init__(self, settings: Settings, output_root: Path, config_path: Optional[Path] = None):
        self.settings = settings
        self.output_root = Path(output_root).expanduser().resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.config_path = config_path
        self.data_dir = data_directory()
        self.cache = FileCache(settings.output.cache_dir or str(self.output_root / "cache"))
        self.tasks: Dict[str, asyncio.Task] = {}

    @staticmethod
    def _text(text: str) -> str:
        if not text.strip() or len(text) > 20000:
            raise ValueError("Provide 1–20000 characters of script text.")
        return text

    @staticmethod
    def _options(aspect: str, resolution: str, top: int) -> str:
        aspect = normalize_aspect(aspect)
        if resolution not in {"4K", "1080", "720"}:
            raise ValueError("Resolution must be 4K, 1080, or 720.")
        if not 1 <= top <= 20:
            raise ValueError("top must be between 1 and 20.")
        return aspect

    def _safe_error(self, error: Exception) -> str:
        message = "{}: {}".format(type(error).__name__, error)

        def mask(value):
            nonlocal message
            if isinstance(value, dict):
                for key, item in value.items():
                    if "key" in key.lower() and isinstance(item, str) and item:
                        for secret in {item, quote(item, safe=""), quote_plus(item)}:
                            message = message.replace(secret, "[redacted]")
                    else:
                        mask(item)
            elif isinstance(value, list):
                for item in value:
                    mask(item)

        mask(self.settings.model_dump())
        return message[:1000]

    async def analyze(self, text: str, aspect: str) -> dict:
        text = self._text(text)
        aspect = normalize_aspect(aspect)
        settings = self.settings.model_copy(deep=True)
        settings.downgrade.planner_fallback = False
        try:
            return model_dump_compat(await analyze_script(text, settings, self.cache, aspect))
        except Exception as exc:
            raise ValueError(self._safe_error(exc)) from None

    async def search(self, query: str, aspect: str, source: str = "all", top: int = 5,
                     resolution: str = "1080", media_type: str = "video") -> dict:
        from cmm.fetcher.registry import PROVIDER_FACTORIES
        self._text(query)
        if len(query) > 500:
            raise ValueError("Search query must be at most 500 characters.")
        aspect = self._options(aspect, resolution, top)
        if source not in {"all", *PROVIDER_FACTORIES} or media_type not in {"video", "image"}:
            raise ValueError("Choose a supported provider and video or image media type.")
        try:
            result = await search_single_query(query, self.settings.model_copy(deep=True), self.cache,
                                               str(self.data_dir), source=source, top_k=top,
                                               aspect=aspect, resolution=resolution, media_type=media_type)
            return model_dump_compat(result)
        except Exception as exc:
            raise ValueError(self._safe_error(exc)) from None

    def start_match(self, text: str, aspect: str, top: int = 3, resolution: str = "1080",
                    download: bool = False, allow_planner_fallback: bool = False,
                    allow_judge_fallback: bool = False, allow_search_fallback: bool = False,
                    allow_generated_fallback: bool = False) -> dict:
        text = self._text(text)
        aspect = self._options(aspect, resolution, top)
        if any(not task.done() for task in self.tasks.values()):
            raise ValueError("A match is already running. Wait for it or cancel_match before starting another.")
        loop = asyncio.get_running_loop()
        settings = self.settings.model_copy(deep=True)
        settings.downgrade.planner_fallback = allow_planner_fallback
        settings.downgrade.judge_fallback = allow_judge_fallback
        settings.downgrade.search_fallback = allow_search_fallback
        settings.downgrade.generated_fallback = allow_generated_fallback
        job_id = uuid4().hex
        folder = self.output_root / job_id
        folder.mkdir()
        record = {"job_id": job_id, "status": "running", "created_at": self._now(),
                  "output_dir": str(folder), "completed_segments": 0, "total_segments": None}
        self._save(record)
        match_input = MatchInput(text=text, aspect=aspect, resolution=resolution,
                                top_results=max(3, top), output_dir=str(folder), save_candidates=download)
        self.tasks[job_id] = loop.create_task(self._run_match(record, match_input, settings))
        return dict(record)

    async def _run_match(self, record: dict, match_input: MatchInput, settings: Settings) -> None:
        def progress(done: int, total: int):
            record.update(completed_segments=done, total_segments=total)
            self._save(record)

        try:
            result = await match_script(match_input, settings, str(self.data_dir),
                                        library_root=settings.library.root or None,
                                        library_meta=settings.library.metadata or None,
                                        progress_callback=progress)
            record.update(status="completed", total_segments=result.total_segments,
                          completed_segments=result.total_segments)
        except asyncio.CancelledError:
            record["status"] = "cancelled"
        except Exception as exc:
            record.update(status="failed", error=self._safe_error(exc))
        finally:
            self._save(record)
            self.tasks.pop(record["job_id"], None)

    def _folder(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("Invalid job_id; use the ID returned by match_script.")
        folder = (self.output_root / job_id).resolve()
        if not folder.is_relative_to(self.output_root):
            raise ValueError("Job directory is outside the configured output root.")
        return folder

    def _save(self, record: dict) -> None:
        record["updated_at"] = self._now()
        folder = self._folder(record["job_id"])
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(record, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, folder / "job.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _read(folder: Path, name: str) -> dict:
        path = (folder / name).resolve()
        if not path.is_relative_to(folder):
            raise ValueError("Result file is outside its job directory.")
        return json.loads(path.read_text(encoding="utf-8"))

    async def get_result(self, job_id: str, offset: int = 0, limit: int = 0, wait_seconds: float = 0) -> dict:
        if offset < 0 or not 0 <= limit <= 20 or not 0 <= wait_seconds <= 30:
            raise ValueError("offset >= 0, limit 0–20, and wait_seconds 0–30 are required.")
        folder = self._folder(job_id)
        task = self.tasks.get(job_id)
        if task and wait_seconds:
            await asyncio.wait({task}, timeout=wait_seconds)
        try:
            record = self._read(folder, "job.json")
        except FileNotFoundError:
            raise ValueError("Unknown job_id in this output root.") from None
        if record["status"] == "running" and job_id not in self.tasks:
            record.update(status="interrupted", error="Server stopped before completion. Start a new match; partial files are retained.")
        record["segments"] = []
        if record["status"] == "completed":
            manifest = self._read(folder, "manifest.json")
            record.update(summary=manifest.get("match_summary", {}), warnings=manifest.get("warnings", []),
                          errors=manifest.get("errors", []),
                          files={name: str(folder / name) for name in (
                              "analysis.json", "manifest.json", "summary.md", "review.html",
                              "segments_overview.csv", "attributions.md")})
            record["segments"] = manifest["segments"][offset:offset + limit] if limit else []
            record["next_offset"] = offset + limit if limit and offset + limit < len(manifest["segments"]) else None
        return record

    async def cancel_match(self, job_id: str) -> dict:
        self._folder(job_id)
        task = self.tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # Cancellation before the coroutine starts still needs a terminal record.
                record = self._read(self._folder(job_id), "job.json")
                record["status"] = "cancelled"
                self._save(record)
                self.tasks.pop(job_id, None)
        return await self.get_result(job_id)

    async def close(self) -> None:
        for job_id in list(self.tasks):
            await self.cancel_match(job_id)

    def doctor(self) -> dict:
        from cmm.cli import _build_doctor_payload
        from cmm.mcp_setup import readiness
        payload = _build_doctor_payload(self.settings, self.config_path)
        payload["mcp"] = {"transport": "stdio", "output_root": str(self.output_root),
                          "data_dir": str(self.data_dir), "max_script_characters": 20000,
                          "max_parallel_matches": 1, "network_verified": False}
        payload["readiness"] = readiness(self.settings)
        return payload

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
