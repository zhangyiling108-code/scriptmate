import asyncio
from pathlib import Path

from cmm.cards.chart_renderer import ChartRenderer
from cmm.config import CardSettings, GenerationSettings
from cmm.models import Segment


def _renderer() -> ChartRenderer:
    return ChartRenderer(CardSettings(), GenerationSettings())


def test_chart_renderer_detects_process_template():
    renderer = _renderer()
    segment = Segment(
        id=1,
        text="植物会影响身体代谢。",
        segment_role="claim",
        visual_type="data_card",
        scene_type="infographic",
        card_text="植物会影响身体代谢。",
        visual_brief="展示代谢机制和身体过程的解释性图示。",
    )

    assert renderer._chart_kind(segment) == "process"


def test_chart_renderer_detects_causal_template():
    renderer = _renderer()
    segment = Segment(
        id=2,
        text="睡眠不足会影响注意力和反应速度。",
        segment_role="claim",
        visual_type="data_card",
        scene_type="infographic",
        card_text="睡眠不足会影响注意力和反应速度。",
        visual_brief="因果关系说明卡。",
    )

    assert renderer._chart_kind(segment) == "causal"


def test_chart_renderer_detects_comparison_template():
    renderer = _renderer()
    segment = Segment(
        id=3,
        text="方案A和方案B的成本对比。",
        segment_role="data_point",
        visual_type="data_card",
        scene_type="infographic",
        card_text="方案A和方案B的成本对比。",
        visual_brief="比较两种方案的差异。",
    )

    assert renderer._chart_kind(segment) == "comparison"


def test_chart_renderer_process_steps_are_domain_aware_for_metabolism():
    renderer = _renderer()
    segment = Segment(
        id=4,
        text="营养摄入会影响身体代谢。",
        segment_role="claim",
        visual_type="data_card",
        scene_type="infographic",
        card_text="营养摄入会影响身体代谢。",
        visual_brief="用流程图展示植物成分如何调节代谢过程。",
    )

    assert renderer._process_steps(segment) == [
        "植物成分进入人体",
        "代谢通路被调节",
        "身体状态出现变化",
    ]
    assert renderer._chart_topic(segment) == "health"


def test_chart_renderer_causal_labels_fallback_when_right_side_empty():
    renderer = _renderer()
    segment = Segment(
        id=5,
        text="植物影响",
        segment_role="claim",
        visual_type="data_card",
        scene_type="infographic",
        card_text="植物影响",
        visual_brief="因果解释卡。",
    )

    assert renderer._causal_labels(segment) == ("植物", "结果变化")


def test_chart_renderer_detects_economy_topic():
    renderer = _renderer()
    segment = Segment(
        id=6,
        text="经济增长会影响消费与投资信心。",
        segment_role="claim",
        visual_type="data_card",
        scene_type="infographic",
        card_text="经济增长会影响消费与投资信心。",
        visual_brief="经济因果解释卡。",
    )

    assert renderer._chart_topic(segment) == "economy"


def test_chart_renderer_render_exposes_chart_kind_metadata(tmp_path: Path):
    renderer = _renderer()
    segment = Segment(
        id=7,
        text="营养摄入会影响身体代谢。",
        segment_role="claim",
        visual_type="data_card",
        scene_type="infographic",
        card_text="营养摄入会影响身体代谢。",
        visual_brief="用流程图展示代谢过程和影响关系。",
    )

    candidate = asyncio.run(renderer.render(segment, str(tmp_path)))

    assert (tmp_path / "chart-7.png").exists()
    assert candidate.source_type == "data_card"
    assert candidate.provider_meta["chart_kind"] == "process"
    assert candidate.provider_meta["chart_topic"] == "health"
    assert candidate.quality_signals["chart_kind"] == "process"
    assert candidate.quality_signals["chart_topic"] == "health"
