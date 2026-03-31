from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw

from cmm.config import CardSettings, GenerationSettings
from cmm.models import MaterialCandidate, Segment


CAUSAL_HINTS = ("影响", "作用", "导致", "提升", "降低", "改善", "抑制", "促进")
PROCESS_HINTS = ("过程", "机制", "代谢", "循环", "通路", "步骤", "原理")
COMPARISON_HINTS = ("对比", "比较", "高于", "低于", "更", "差异", "优于", "vs")
BODY_HINTS = ("身体", "人体", "细胞", "吸收", "器官", "健康")
PLANT_HINTS = ("植物", "草本", "营养", "食物", "成分")
ECONOMY_HINTS = ("经济", "市场", "增长", "投资", "消费", "产业")


class ChartRenderer:
    def __init__(self, settings: CardSettings, generation: GenerationSettings):
        self.settings = settings
        self.generation = generation

    async def render(self, segment: Segment, output_dir: str) -> MaterialCandidate:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / "chart-{0}.png".format(segment.id)
        chart_kind = self._chart_kind(segment)
        chart_topic = self._chart_topic(segment)
        self._draw_chart(segment, output_path, chart_kind, chart_topic)
        return MaterialCandidate(
            id="data_card:{0}".format(segment.id),
            source_type="data_card",
            media_type="image",
            uri=str(output_path),
            thumbnail_url=str(output_path),
            preview_uri=str(output_path),
            source_page=str(output_path),
            relevance_score=0.88,
            match_level="exact",
            reason="Generated data chart fallback for numeric or comparison-heavy segment.",
            license_type="generated",
            attribution_required=False,
            width=self.settings.width,
            height=self.settings.height,
            tags=segment.keywords_cn or segment.keywords_en,
            quality_signals={
                "generated": True,
                "chart_style": self.generation.chart_style,
                "chart_kind": chart_kind,
                "chart_topic": chart_topic,
            },
            provider_meta={
                "chart_style": self.generation.chart_style,
                "chart_kind": chart_kind,
                "chart_topic": chart_topic,
            },
        )

    def _draw_chart(self, segment: Segment, output_path: Path, chart_kind: str, chart_topic: str) -> None:
        width = self.settings.width
        height = self.settings.height
        bg = (22, 30, 42) if self.generation.chart_style == "dark_professional" else (247, 243, 232)
        fg = (236, 244, 255) if self.generation.chart_style == "dark_professional" else (25, 32, 44)
        accent, accent_soft, accent_warm = self._palette(chart_topic)

        image = Image.new("RGB", (width, height), color=bg)
        draw = ImageDraw.Draw(image)
        title = segment.card_text or segment.text
        draw.text((80, 72), self._subtitle(chart_kind, chart_topic), fill=accent_warm)
        draw.text((80, 126), title[:30], fill=fg)

        if chart_kind == "causal":
            self._draw_causal_card(draw, segment, fg, accent, accent_soft, accent_warm, width, height)
        elif chart_kind == "process":
            self._draw_process_card(draw, segment, fg, accent, accent_soft, accent_warm, width, height)
        elif chart_kind == "comparison":
            self._draw_comparison_card(draw, segment, fg, accent, accent_soft, accent_warm, width, height)
        else:
            self._draw_bar_card(draw, segment, fg, accent, width, height)

        draw.text((80, height - 120), "ScriptMate {0} explainer".format(chart_topic), fill=fg)
        image.save(output_path)

    def _draw_causal_card(
        self,
        draw: ImageDraw.ImageDraw,
        segment: Segment,
        fg: Tuple[int, int, int],
        accent: Tuple[int, int, int],
        accent_soft: Tuple[int, int, int],
        accent_warm: Tuple[int, int, int],
        width: int,
        height: int,
    ) -> None:
        left_box = (90, 360, width // 2 - 40, 760)
        right_box = (width // 2 + 40, 360, width - 90, 760)
        self._rounded_box(draw, left_box, accent_soft)
        self._rounded_box(draw, right_box, accent)
        left_label, right_label = self._causal_labels(segment)
        draw.text((left_box[0] + 34, left_box[1] + 34), "因素", fill=fg)
        draw.text((left_box[0] + 34, left_box[1] + 120), left_label[:38], fill=fg)
        draw.text((right_box[0] + 34, right_box[1] + 34), "结果", fill=fg)
        draw.text((right_box[0] + 34, right_box[1] + 120), right_label[:38], fill=fg)
        mid_y = (left_box[1] + left_box[3]) // 2
        draw.line((left_box[2] + 15, mid_y, right_box[0] - 25, mid_y), fill=accent_warm, width=10)
        draw.polygon(
            [(right_box[0] - 28, mid_y - 28), (right_box[0] - 28, mid_y + 28), (right_box[0] + 8, mid_y)],
            fill=accent_warm,
        )
        draw.text((100, 860), self._body_excerpt(segment, 120), fill=fg)

    def _draw_process_card(
        self,
        draw: ImageDraw.ImageDraw,
        segment: Segment,
        fg: Tuple[int, int, int],
        accent: Tuple[int, int, int],
        accent_soft: Tuple[int, int, int],
        accent_warm: Tuple[int, int, int],
        width: int,
        height: int,
    ) -> None:
        steps = self._process_steps(segment)
        top = 330
        box_h = 220
        for index, step in enumerate(steps):
            y1 = top + index * 270
            y2 = y1 + box_h
            color = accent_soft if index % 2 == 0 else accent
            box = (110, y1, width - 110, y2)
            self._rounded_box(draw, box, color)
            draw.text((box[0] + 30, box[1] + 24), "STEP {0}".format(index + 1), fill=fg)
            draw.text((box[0] + 30, box[1] + 90), step[:52], fill=fg)
            if index < len(steps) - 1:
                center_x = width // 2
                draw.line((center_x, y2 + 10, center_x, y2 + 54), fill=accent_warm, width=8)
                draw.polygon([(center_x - 22, y2 + 50), (center_x + 22, y2 + 50), (center_x, y2 + 82)], fill=accent_warm)

    def _draw_comparison_card(
        self,
        draw: ImageDraw.ImageDraw,
        segment: Segment,
        fg: Tuple[int, int, int],
        accent: Tuple[int, int, int],
        accent_soft: Tuple[int, int, int],
        accent_warm: Tuple[int, int, int],
        width: int,
        height: int,
    ) -> None:
        labels = self._comparison_labels(segment)
        values = self._extract_numbers(segment.text)[:2] or [56, 81]
        if len(values) == 1:
            values.append(max(1, values[0] + 15))
        max_value = max(values)
        chart_bottom = height - 320
        chart_top = 520
        columns = [(220, 360, accent_soft), (width - 360, width - 220, accent)]
        for idx, (x1, x2, color) in enumerate(columns):
            normalized = values[idx] / max_value if max_value else 0.5
            y1 = chart_bottom - int((chart_bottom - chart_top) * normalized)
            draw.rectangle((x1, y1, x2, chart_bottom), fill=color)
            draw.text((x1, chart_bottom + 28), labels[idx][:18], fill=fg)
            draw.text((x1 + 12, y1 - 42), str(values[idx]), fill=fg)
        draw.text((80, 390), self._body_excerpt(segment, 80), fill=fg)
        draw.text((80, height - 180), "对比视图突出差异与方向。", fill=accent_warm)

    def _draw_bar_card(
        self,
        draw: ImageDraw.ImageDraw,
        segment: Segment,
        fg: Tuple[int, int, int],
        accent: Tuple[int, int, int],
        width: int,
        height: int,
    ) -> None:
        numbers = self._extract_numbers(segment.text)
        values = numbers[:4] if numbers else [45, 72, 88]
        labels = ["A", "B", "C", "D"][: len(values)]
        max_value = max(values) if values else 1
        chart_bottom = height - 220
        chart_top = 320
        chart_left = 100
        bar_gap = 40
        bar_width = 120
        for index, value in enumerate(values):
            x1 = chart_left + index * (bar_width + bar_gap)
            x2 = x1 + bar_width
            normalized = value / max_value if max_value else 0.5
            y1 = chart_bottom - int((chart_bottom - chart_top) * normalized)
            draw.rectangle((x1, y1, x2, chart_bottom), fill=accent)
            draw.text((x1 + 15, chart_bottom + 20), labels[index], fill=fg)
            draw.text((x1 + 10, y1 - 30), str(value), fill=fg)

    def _rounded_box(self, draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], fill: Tuple[int, int, int]) -> None:
        draw.rounded_rectangle(box, radius=28, fill=fill)

    def _chart_kind(self, segment: Segment) -> str:
        text = "{0} {1}".format(segment.text, segment.visual_brief)
        if any(hint in text for hint in COMPARISON_HINTS):
            return "comparison"
        if any(hint in text for hint in PROCESS_HINTS):
            return "process"
        if any(hint in text for hint in CAUSAL_HINTS):
            return "causal"
        return "bar"

    def _subtitle(self, chart_kind: str, chart_topic: str) -> str:
        base = {
            "causal": "CAUSE / EFFECT",
            "process": "PROCESS FLOW",
            "comparison": "COMPARE",
            "bar": "DATA SNAPSHOT",
        }.get(chart_kind, "DATA SNAPSHOT")
        topic = {
            "health": "HEALTH",
            "economy": "ECONOMY",
            "general": "EXPLAINER",
        }.get(chart_topic, "EXPLAINER")
        return "{0} / {1}".format(topic, base)

    def _palette(self, chart_topic: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]:
        if self.generation.chart_style == "dark_professional":
            palettes = {
                "health": ((76, 198, 146), (118, 224, 182), (231, 187, 86)),
                "economy": ((76, 175, 255), (125, 205, 255), (237, 171, 84)),
                "general": ((161, 120, 255), (195, 171, 255), (237, 171, 84)),
            }
        else:
            palettes = {
                "health": ((64, 148, 118), (135, 196, 170), (193, 126, 46)),
                "economy": ((57, 120, 210), (109, 153, 220), (193, 126, 46)),
                "general": ((114, 92, 179), (176, 158, 223), (193, 126, 46)),
            }
        return palettes.get(chart_topic, palettes["general"])

    def _causal_labels(self, segment: Segment) -> Tuple[str, str]:
        text = segment.card_text or segment.text
        if "影响" in text:
            left, right = text.split("影响", 1)
            return (left.strip("。；， ") or "关键因素", right.strip("。；， ") or "结果变化")
        if "作用" in text:
            left, right = text.split("作用", 1)
            return (left.strip("。；， ") or "关键因素", right.strip("。；， ") or "结果变化")
        if "导致" in text:
            left, right = text.split("导致", 1)
            return (left.strip("。；， ") or "前置条件", right.strip("。；， ") or "结果变化")
        return ("关键因素", self._body_excerpt(segment, 26))

    def _process_steps(self, segment: Segment) -> List[str]:
        parts = re.split(r"[，、；]", segment.card_text or segment.text)
        steps = [part.strip("。 ") for part in parts if part.strip("。 ")]
        if len(steps) >= 3:
            return steps[:3]
        text = "{0} {1}".format(segment.card_text or segment.text, segment.visual_brief)
        if any(hint in text for hint in PLANT_HINTS) and any(hint in text for hint in PROCESS_HINTS):
            return ["植物成分进入人体", "代谢通路被调节", "身体状态出现变化"]
        if any(hint in text for hint in BODY_HINTS) and any(hint in text for hint in PROCESS_HINTS):
            return ["外部信号输入", "体内过程发生调节", "最终结果被观察到"]
        if any(hint in text for hint in ECONOMY_HINTS):
            return ["经济信号出现", "市场环节传导", "指标结果变化"]
        base = self._body_excerpt(segment, 20)
        return ["输入信号", base or "触发过程", "结果变化"]

    def _chart_topic(self, segment: Segment) -> str:
        text = "{0} {1}".format(segment.card_text or segment.text, segment.visual_brief)
        if any(hint in text for hint in BODY_HINTS + PLANT_HINTS):
            return "health"
        if any(hint in text for hint in ECONOMY_HINTS):
            return "economy"
        return "general"

    def _comparison_labels(self, segment: Segment) -> List[str]:
        if "对比" in segment.text or "比较" in segment.text:
            parts = re.split(r"[，、；和与]", segment.text)
            cleaned = [part.strip("。 ") for part in parts if part.strip("。 ")]
            if len(cleaned) >= 2:
                return [cleaned[0][:18], cleaned[1][:18]]
        return ["方案 A", "方案 B"]

    def _body_excerpt(self, segment: Segment, limit: int) -> str:
        text = (segment.card_text or segment.text).strip()
        return text[:limit]

    def _extract_numbers(self, text: str) -> List[int]:
        values = []
        for token in re.findall(r"\d+(?:\.\d+)?", text):
            try:
                values.append(int(float(token)))
            except ValueError:
                continue
        return values
