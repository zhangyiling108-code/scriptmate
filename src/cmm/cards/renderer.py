from __future__ import annotations

from pathlib import Path

from jinja2 import Template
from PIL import Image, ImageDraw

from cmm.cards.context_builder import build_card_context
from cmm.config import CardSettings
from cmm.models import MaterialCandidate, Segment


class CardRenderer:
    def __init__(self, template_dir: str, settings: CardSettings):
        self.template_dir = Path(template_dir)
        self.settings = settings

    async def render(self, segment: Segment, output_dir: str, score_override: float = 0.95) -> MaterialCandidate:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = "segment-{0}.png".format(segment.id)
        output_path = target_dir / filename
        context = build_card_context(segment)
        html = self._render_html(segment, context)
        try:
            await self._render_with_playwright(html, output_path)
        except Exception:
            self._render_with_pillow(context, output_path)

        return MaterialCandidate(
            id="{0}:{1}".format("data_card" if segment.visual_type == "data_card" else "text_card", segment.id),
            source_type="data_card" if segment.visual_type == "data_card" else "text_card",
            media_type="image",
            uri=str(output_path),
            thumbnail_url=str(output_path),
            preview_uri=str(output_path),
            source_page=str(output_path),
            relevance_score=score_override,
            match_level="exact",
            reason="Generated fallback card for this segment.",
            license_type="generated",
            attribution_required=False,
            width=self.settings.width,
            height=self.settings.height,
            tags=segment.keywords_cn or segment.keywords_en,
            quality_signals={"generated": True},
            provider_meta={"template": self._template_name(segment), "html": html},
        )

    def _render_html(self, segment: Segment, context: dict) -> str:
        template_path = self.template_dir / self._template_name(segment)
        template = Template(template_path.read_text(encoding="utf-8"))
        return template.render(**context)

    async def _render_with_playwright(self, html: str, output_path: Path) -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page(viewport={"width": self.settings.width, "height": self.settings.height})
            await page.set_content(html)
            await page.screenshot(path=str(output_path), full_page=True)
            await browser.close()

    def _render_with_pillow(self, context: dict, output_path: Path) -> None:
        if self.settings.theme == "atlas":
            background = (236, 227, 203)
            title_color = (74, 55, 35)
            body_color = (82, 68, 49)
            keyword_color = (112, 86, 50)
        else:
            background = (247, 243, 232)
            title_color = (28, 36, 48)
            body_color = (60, 70, 84)
            keyword_color = (110, 90, 60)

        image = Image.new("RGB", (self.settings.width, self.settings.height), color=background)
        draw = ImageDraw.Draw(image)
        draw.text((60, 80), context["title"], fill=title_color)
        draw.text((60, 180), context["body"][:160], fill=body_color)
        if context["keywords"]:
            draw.text((60, self.settings.height - 120), context["keywords"], fill=keyword_color)
        image.save(output_path)

    def _template_name(self, segment: Segment) -> str:
        prefix = "atlas_" if self.settings.theme == "atlas" else ""
        if segment.visual_type == "text_card" or segment.scene_type == "text_card":
            return prefix + "bullet_card.html"
        if segment.visual_type == "data_card" or segment.scene_type == "infographic":
            return prefix + "data_card.html"
        return prefix + "title_card.html"
