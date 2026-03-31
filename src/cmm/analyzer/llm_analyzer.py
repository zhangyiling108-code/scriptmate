from __future__ import annotations

import asyncio
import json
import re
from typing import Dict, List

from pydantic import ValidationError

from cmm.analyzer.base import BaseAnalyzer
from cmm.config import ModelSettings
from cmm.exceptions import AnalyzerError
from cmm.models import AnalysisResult, Segment
from cmm.utils.http import build_async_client
from cmm.utils.retry import with_retry


ROLE_HINTS = {
    "summary": ("summary", "text_card", "text_card"),
    "总结": ("summary", "text_card", "text_card"),
    "结论": ("summary", "text_card", "text_card"),
    "数据": ("data_point", "data_card", "infographic"),
    "增长": ("data_point", "data_card", "infographic"),
    "GDP": ("data_point", "data_card", "infographic"),
    "对比": ("example", "data_card", "infographic"),
    "比如": ("example", "stock_video", "b_roll"),
    "例如": ("example", "stock_video", "b_roll"),
    "经济": ("claim", "stock_video", "b_roll"),
    "货币": ("claim", "stock_video", "b_roll"),
    "植物": ("explanation", "stock_video", "b_roll"),
    "代谢": ("explanation", "data_card", "infographic"),
}
SUMMARY_HINTS = ("总结", "最后", "结论", "一句话", "归根到底")
HOOK_HINTS = ("大家好", "今天聊", "这一期", "这次说")
EXPLANATORY_INFOGRAPHIC_HINTS = ("代谢", "机制", "作用", "影响", "原理", "过程", "关系", "通路")
ECONOMY_INFOGRAPHIC_HINTS = ("经济", "市场", "消费", "投资", "产业", "需求", "供给", "信心")
CONCRETE_SCENE_HINTS = ("城市", "天际线", "高楼", "车流", "街道", "工厂", "港口", "人群", "办公室")


class LLMAnalyzer(BaseAnalyzer):
    def __init__(self, settings: ModelSettings, allow_fallback: bool = False):
        self.settings = settings
        self.allow_fallback = allow_fallback

    async def analyze(self, text: str, aspect: str) -> AnalysisResult:
        try:
            return await self._remote_analyze(text, aspect)
        except Exception:
            if not self.allow_fallback:
                raise
            return self._heuristic_analyze(text, aspect)

    async def _remote_analyze(self, text: str, aspect: str) -> AnalysisResult:
        if not self.settings.base_url or not self.settings.api_key:
            raise AnalyzerError("Planner model requires base_url and api_key.")

        prompts = [
            self._build_prompt(text, aspect),
            self._build_retry_prompt(text, aspect),
        ]
        last_error = None
        for prompt in prompts:
            try:
                content = await asyncio.wait_for(
                    self._request_completion(prompt),
                    timeout=max(float(self.settings.timeout_seconds), 5.0) + 3.0,
                )
                parsed = self._normalize_analysis_payload(
                    json.loads(self._sanitize_json_text(self._extract_json(content))),
                    aspect,
                    text,
                )
                return AnalysisResult(**parsed)
            except Exception as exc:
                last_error = exc
                continue
        raise AnalyzerError("Planner model returned invalid structured output.") from last_error

    async def _request_completion(self, prompt: str) -> str:
        headers = {"Authorization": "Bearer {0}".format(self.settings.api_key)}
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": "You are a strict JSON generator. Return JSON only, with no markdown fences."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        timeout = max(float(self.settings.timeout_seconds), 5.0)
        async def _request() -> str:
            async with build_async_client(timeout=timeout) as client:
                response = await client.post(
                    "{0}/chat/completions".format(self.settings.base_url.rstrip("/")),
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

        return await with_retry(_request, retries=max(self.settings.max_retries, 0), delay=0.4)

    def _heuristic_analyze(self, text: str, aspect: str) -> AnalysisResult:
        lines = [item.strip() for item in re.split(r"[。\n]+", text) if item.strip()]
        segments: List[Segment] = []
        for idx, line in enumerate(lines or [text.strip()], start=1):
            segment_role = "explanation"
            visual_type = "stock_video"
            scene_type = "b_roll"
            for hint, result in ROLE_HINTS.items():
                if hint.lower() in line.lower():
                    segment_role, visual_type, scene_type = result
                    break
            if idx == 1 and any(hint in line for hint in HOOK_HINTS):
                segment_role = "hook"
                visual_type = "skip"
                scene_type = "talking_head"
            if any(hint in line for hint in SUMMARY_HINTS):
                segment_role = "summary"
                visual_type = "text_card"
                scene_type = "text_card"

            english_queries = self._build_query_layers(line)
            segments.append(
                Segment(
                    id=idx,
                    text=line,
                    segment_role=segment_role,
                    visual_type=visual_type,
                    scene_type=scene_type,
                    duration_hint=max(2.0, min(6.0, round(len(line) / 12, 1))),
                    search_queries=english_queries["l1"] + english_queries["l2"],
                    search_query_layers=english_queries,
                    narrative_subject="",
                    context_statement="",
                    context_tags=[],
                    keywords_cn=[line[:10]],
                    keywords_en=english_queries["l1"][:2],
                    card_text=line if visual_type in {"data_card", "text_card"} else "",
                    visual_brief="heuristic fallback visual plan",
                )
            )
        return AnalysisResult(segments=self._postprocess_segments(segments), overall_style="heuristic fallback", target_aspect=aspect)

    def _build_prompt(self, text: str, aspect: str) -> str:
        return (
            "Analyze this Chinese script for a material matching engine. "
            "Return one JSON object with keys segments, overall_style, target_aspect. "
            "Each segment must include id, text, segment_role, visual_type, scene_type, "
            "search_queries, search_query_layers, keywords_cn, keywords_en, card_text, visual_brief, narrative_subject, context_statement, context_tags. "
            "Allowed segment_role: hook, claim, explanation, example, data_point, summary. "
            "Allowed visual_type: stock_video, stock_image, data_card, text_card, skip. "
            "Allowed scene_type: talking_head, b_roll, infographic, text_card. "
            "Use skip only for intro or host-only lines. "
            "Use data_card for numbers, charts, comparisons, or abstract processes that are better visualized than searched. "
            "Use stock_image instead of stock_video when the segment is explanatory but visually abstract, such as health concepts, body processes, metabolism, mechanisms, or plant-to-health relationships. "
            "Prefer stock_video only when there is a clear real-world scene, action, place, or object that can be filmed directly. "
            "Use text_card for explicit summary or emphasis. "
            "Avoid generic stock footage plans for abstract explanations. "
            "search_query_layers must be an object with keys l1, l2, l3, l4. "
            "narrative_subject should summarize the full-script subject in a short English phrase. "
            "context_statement should explain this segment in the full-script context, including country/domain when relevant. "
            "context_tags should capture geography, domain, and narrative-object constraints. "
            "search_queries and keywords_en must be English and suitable for stock search.\n"
            "Target aspect: {0}\nScript:\n{1}".format(aspect, text)
        )

    def _build_retry_prompt(self, text: str, aspect: str) -> str:
        return (
            "Return one valid JSON object only. No explanations, no markdown. "
            "All ids must be integers. Do not invent placeholder segments. "
            "Schema keys: segments, overall_style, target_aspect. "
            "Segment keys: id, text, segment_role, visual_type, scene_type, search_queries, search_query_layers, keywords_cn, keywords_en, card_text, visual_brief, narrative_subject, context_statement, context_tags. "
            "The first short greeting segment may use visual_type=skip. "
            "Summary lines should use visual_type=text_card. "
            "Data and comparisons should use visual_type=data_card. "
            "Abstract explanatory concepts like metabolism, health effects, internal mechanisms, or concept relationships should prefer stock_image or data_card over stock_video. "
            "Search strategy must follow full-paragraph context, country, and narrative subject, not isolated keywords. "
            "Target aspect: {0}\nScript:\n{1}".format(aspect, text)
        )

    def _extract_json(self, content: str) -> str:
        start = content.find("{")
        if start == -1:
            raise AnalyzerError("Planner response does not contain JSON.")
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(content)):
            char = content[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return content[start : index + 1]
        raise AnalyzerError("Planner response does not contain a complete JSON object.")

    def _sanitize_json_text(self, raw: str) -> str:
        sanitized = raw.replace("\r", "\\r").replace("\t", "\\t")
        return re.sub(r"[\x00-\x08\x0b-\x1f]", " ", sanitized)

    def _normalize_analysis_payload(self, payload: Dict[str, object], aspect: str, original_text: str = "") -> Dict[str, object]:
        raw_segments = payload.get("segments", [])
        normalized_segments: List[Segment] = []
        for index, raw_segment in enumerate(raw_segments, start=1):
            if not isinstance(raw_segment, dict):
                continue
            query_layers = raw_segment.get("search_query_layers") or self._build_query_layers(str(raw_segment.get("text", "")))
            segment = Segment(
                id=self._normalize_segment_id(raw_segment.get("id"), index),
                text=str(raw_segment.get("text", "")).strip(),
                segment_role=self._normalize_segment_role(raw_segment.get("segment_role")),
                visual_type=self._normalize_visual_type(raw_segment.get("visual_type")),
                scene_type=self._normalize_scene_type(raw_segment.get("scene_type"), raw_segment.get("visual_type")),
                duration_hint=self._normalize_duration(raw_segment.get("duration_hint")),
                narrative_subject=str(raw_segment.get("narrative_subject", "") or ""),
                context_statement=str(raw_segment.get("context_statement", "") or ""),
                context_tags=self._ensure_list(raw_segment.get("context_tags")),
                search_queries=self._ensure_list(raw_segment.get("search_queries")),
                search_query_layers=self._normalize_query_layers(query_layers),
                keywords_cn=self._ensure_list(raw_segment.get("keywords_cn")),
                keywords_en=self._ensure_list(raw_segment.get("keywords_en")),
                card_text=str(raw_segment.get("card_text", "") or ""),
                visual_brief=str(raw_segment.get("visual_brief", "") or ""),
            )
            normalized_segments.append(segment)
        payload["segments"] = [segment.model_dump() for segment in self._postprocess_segments(normalized_segments, original_text)]
        payload["overall_style"] = str(payload.get("overall_style", "clean documentary"))
        payload["target_aspect"] = str(payload.get("target_aspect", aspect))
        return payload

    def _normalize_segment_id(self, value, fallback_index: int) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            match = re.search(r"(\d+)", value)
            if match:
                return int(match.group(1))
        return fallback_index

    def _normalize_duration(self, value) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)]
            if not numbers:
                return 3.0
            if len(numbers) == 1:
                return numbers[0]
            return round(sum(numbers[:2]) / 2.0, 1)
        return 3.0

    def _normalize_segment_role(self, value) -> str:
        value_str = str(value or "").lower()
        if value_str in {"hook", "claim", "explanation", "example", "data_point", "summary"}:
            return value_str
        return "explanation"

    def _normalize_visual_type(self, value) -> str:
        value_str = str(value or "").lower()
        if value_str in {"stock_video", "stock_image", "data_card", "text_card", "skip"}:
            return value_str
        if "data" in value_str or "chart" in value_str:
            return "data_card"
        if "text" in value_str or "summary" in value_str:
            return "text_card"
        if "skip" in value_str or "talk" in value_str:
            return "skip"
        if "image" in value_str:
            return "stock_image"
        return "stock_video"

    def _normalize_scene_type(self, value, visual_type) -> str:
        value_str = str(value or "").lower()
        if value_str in {"talking_head", "b_roll", "infographic", "text_card"}:
            return value_str
        visual_type = self._normalize_visual_type(visual_type)
        if visual_type == "skip":
            return "talking_head"
        if visual_type in {"data_card", "stock_image"}:
            return "infographic"
        if visual_type == "text_card":
            return "text_card"
        return "b_roll"

    def _ensure_list(self, value) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _normalize_query_layers(self, value) -> Dict[str, List[str]]:
        if not isinstance(value, dict):
            return self._build_query_layers("")
        normalized = {}
        for key in ("l1", "l2", "l3", "l4"):
            normalized[key] = self._ensure_list(value.get(key))
        if not any(normalized.values()):
            return self._build_query_layers("")
        return normalized

    def _build_query_layers(self, text: str) -> Dict[str, List[str]]:
        lowered = text.lower()
        direct = self._query_terms(lowered)
        synonyms = []
        metaphors = []
        mood = []
        if "gdp" in lowered or "经济" in text:
            direct.extend(["economic growth", "gdp growth"])
            synonyms.extend(["financial growth", "economy growth"])
            metaphors.extend(["city skyline prosperity"])
            mood.extend(["business optimism"])
        if "中国" in text or "china" in lowered:
            direct.extend(["china economy", "china development"])
            synonyms.extend(["china skyline", "china infrastructure"])
        if "货币" in text or "现金" in text:
            direct.extend(["currency", "banknotes"])
            synonyms.extend(["money", "coins"])
        if "高铁" in text:
            direct.extend(["china high speed rail", "china bullet train"])
            synonyms.extend(["high speed train china", "rail infrastructure china"])
        if "港珠澳" in text or "大桥" in text:
            direct.extend(["china sea bridge", "bridge infrastructure china"])
            synonyms.extend(["hong kong zhuhai macau bridge", "china bridge aerial"])
        if "5g" in lowered or "基站" in text:
            direct.extend(["china 5g tower", "cell tower china"])
            synonyms.extend(["telecommunication tower china", "5g infrastructure china"])
        if "新能源" in text:
            direct.extend(["china electric vehicle factory", "new energy factory china"])
            synonyms.extend(["battery production china", "electric car assembly china"])
        if "航天" in text or "航海" in text:
            direct.extend(["china rocket launch", "china aerospace"])
            synonyms.extend(["satellite launch china", "shipyard technology china"])
        if "植物" in text:
            direct.extend(["plants close up", "green leaves"])
            synonyms.extend(["herbal plants", "botanical ingredients"])
        if "代谢" in text:
            direct.extend(["cellular metabolism", "human metabolism"])
            synonyms.extend(["microscope cells", "body metabolism"])
            metaphors.extend(["glowing cells illustration"])
        return {
            "l1": self._dedupe(direct)[:2],
            "l2": self._dedupe(synonyms)[:3],
            "l3": self._dedupe(metaphors)[:2],
            "l4": self._dedupe(mood)[:2],
        }

    def _query_terms(self, text: str) -> List[str]:
        sanitized = re.sub(r"[^\w\s]+", " ", text)
        pieces = [piece for piece in sanitized.split() if len(piece) >= 2]
        return [" ".join(pieces[:2])] if pieces else ["documentary footage"]

    def _dedupe(self, items: List[str]) -> List[str]:
        seen = set()
        ordered = []
        for item in items:
            normalized = " ".join(str(item).split()).strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(normalized)
        return ordered

    def _postprocess_segments(self, segments: List[Segment], original_text: str = "") -> List[Segment]:
        cleaned = [segment for segment in segments if segment.text.strip()]
        if not cleaned:
            return []
        context = self._build_document_context(cleaned, original_text)
        for index, segment in enumerate(cleaned, start=1):
            segment.id = index
            segment.narrative_subject = segment.narrative_subject or context["narrative_subject"]
            segment.context_tags = self._merge_terms(segment.context_tags, context["context_tags"])
            if index == 1 and (segment.visual_type == "skip" or any(hint in segment.text for hint in HOOK_HINTS)):
                segment.segment_role = "hook"
                segment.visual_type = "skip"
                segment.scene_type = "talking_head"
                segment.card_text = ""
            if any(hint in segment.text for hint in SUMMARY_HINTS):
                segment.segment_role = "summary"
                segment.visual_type = "text_card"
                segment.scene_type = "text_card"
                segment.card_text = segment.text
            if self._should_force_infographic_card(segment):
                segment.visual_type = "data_card"
                segment.scene_type = "infographic"
                segment.card_text = segment.card_text or segment.text
            if segment.visual_type == "data_card":
                segment.scene_type = "infographic"
                segment.card_text = segment.card_text or segment.text
            if segment.visual_type == "stock_image":
                segment.scene_type = "infographic"
            if segment.visual_type == "stock_video":
                segment.scene_type = "b_roll"
            if not segment.search_queries:
                segment.search_queries = segment.search_query_layers.get("l1", []) + segment.search_query_layers.get("l2", [])
            if not segment.keywords_en:
                segment.keywords_en = segment.search_query_layers.get("l1", [])
            self._apply_context_to_segment(segment, context)
        return cleaned

    def _apply_context_to_segment(self, segment: Segment, context: Dict[str, object]) -> None:
        subject = str(context.get("narrative_subject", "") or "").strip()
        context_tags = list(context.get("context_tags", []))
        if not segment.context_statement:
            segment.context_statement = "{0}: {1}".format(subject, segment.text[:80]).strip(": ")

        context_queries: List[str] = []
        if subject:
            context_queries.append(subject)
        context_queries.extend(context_tags[:4])
        if segment.scene_type == "b_roll" and subject:
            context_queries.append("{0} documentary footage".format(subject))
        if segment.visual_type == "stock_image" and subject:
            context_queries.append("{0} editorial image".format(subject))
        if segment.scene_type == "infographic" and subject:
            context_queries.append("{0} explanatory reference".format(subject))

        existing = segment.search_query_layers.get("context", [])
        segment.search_query_layers["context"] = self._merge_terms(existing, context_queries)
        segment.search_queries = self._merge_terms(
            segment.search_queries,
            segment.search_query_layers.get("l1", [])
            + segment.search_query_layers.get("l2", [])
            + segment.search_query_layers.get("context", []),
        )
        segment.keywords_en = self._merge_terms(segment.keywords_en, context_tags[:4])

    def _build_document_context(self, segments: List[Segment], original_text: str = "") -> Dict[str, object]:
        full_text = "{0} {1}".format(original_text, " ".join(segment.text for segment in segments)).strip()
        lowered = full_text.lower()
        context_tags: List[str] = []
        subject_parts: List[str] = []

        geo_map = [
            ("china", ("中国", "china", "我国")),
            ("united states", ("美国", "u.s.", "usa", "chatgpt", "openai", "anthropic", "google deepmind", "meta ai", "xai")),
            ("global", ("全球", "world", "世界")),
        ]
        for label, hints in geo_map:
            if any(hint.lower() in lowered for hint in hints):
                context_tags.append(label)
                subject_parts.append(label)
                break

        domain_map = [
            ("economy", ("经济", "gdp", "投资", "消费", "基建", "制造", "产业")),
            ("artificial intelligence", ("人工智能", "ai", "chatgpt", "gpt", "agent", "gpu", "llama", "gemini", "claude")),
            ("cardiac health", ("心源性猝死", "心脏", "猝死", "aed", "心电", "cpr", "室颤")),
            ("medical science", ("医疗", "病理", "心肌", "离子通道", "冠心病", "诊断")),
        ]
        for label, hints in domain_map:
            if any(hint.lower() in lowered for hint in hints):
                context_tags.append(label)
                subject_parts.append(label)
                break

        narrative_map = [
            ("development story", ("二十年", "增长", "转型", "引领")),
            ("competition story", ("竞赛", "竞争", "角力", "战争")),
            ("emergency prevention story", ("急救", "预防", "识别", "救援")),
        ]
        for label, hints in narrative_map:
            if any(hint.lower() in lowered for hint in hints):
                context_tags.append(label)
                subject_parts.append(label)
                break

        if not subject_parts:
            subject_parts.append("documentary explainer")

        return {
            "narrative_subject": " ".join(subject_parts[:3]),
            "context_tags": self._merge_terms([], context_tags),
        }

    def _merge_terms(self, base: List[str], extra: List[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for item in list(base) + list(extra):
            normalized = " ".join(str(item).split()).strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(normalized)
        return merged

    def _should_force_infographic_card(self, segment: Segment) -> bool:
        if segment.segment_role not in {"claim", "explanation", "data_point"}:
            return False
        if segment.visual_type not in {"stock_image", "stock_video", "data_card"}:
            return False

        text = segment.text
        if any(hint in text for hint in EXPLANATORY_INFOGRAPHIC_HINTS):
            return True

        has_economy_hint = any(hint in text for hint in ECONOMY_INFOGRAPHIC_HINTS)
        has_explanatory_shape = any(hint in text for hint in ("影响", "作用", "导致", "关系", "对比", "比较", "变化"))
        has_concrete_scene = any(hint in text for hint in CONCRETE_SCENE_HINTS)
        return has_economy_hint and has_explanatory_shape and not has_concrete_scene
