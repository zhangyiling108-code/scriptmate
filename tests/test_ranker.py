from cmm.models import MaterialCandidate, Segment
from cmm.ranker.relevance import Ranker


def test_ranker_does_not_let_resolution_overpower_relevance():
    ranker = Ranker()
    segment = Segment(id=1, text="植物会影响身体代谢。", visual_type="stock_image", scene_type="infographic")

    weaker_large = MaterialCandidate(
        id="pixabay-image:weak",
        source_type="pixabay",
        media_type="image",
        uri="https://example.com/weak.jpg",
        relevance_score=0.60,
        match_level="generic",
        width=6000,
        height=4000,
    )
    stronger_smaller = MaterialCandidate(
        id="pixabay-image:strong",
        source_type="pixabay",
        media_type="image",
        uri="https://example.com/strong.jpg",
        relevance_score=0.85,
        match_level="exact",
        width=3529,
        height=4705,
    )

    matched = ranker.match([segment], {1: [weaker_large, stronger_smaller]})

    assert matched[0].primary is not None
    assert matched[0].primary.id == "pixabay-image:strong"


def test_ranker_shortlist_prefers_diverse_candidates_over_same_source_duplicates():
    ranker = Ranker()
    segment = Segment(id=1, text="城市经济活力。", visual_type="stock_video", scene_type="b_roll")

    candidates = [
        MaterialCandidate(
            id="pexels:1",
            source_type="pexels",
            media_type="video",
            uri="https://example.com/1.mp4",
            relevance_score=0.92,
            match_level="exact",
            provider_meta={"title": "City skyline"},
        ),
        MaterialCandidate(
            id="pexels:2",
            source_type="pexels",
            media_type="video",
            uri="https://example.com/2.mp4",
            relevance_score=0.90,
            match_level="exact",
            provider_meta={"title": "City skyline"},
        ),
        MaterialCandidate(
            id="pixabay:3",
            source_type="pixabay",
            media_type="video",
            uri="https://example.com/3.mp4",
            relevance_score=0.86,
            match_level="approx",
            provider_meta={"title": "Busy traffic"},
        ),
        MaterialCandidate(
            id="data_card:4",
            source_type="data_card",
            media_type="image",
            uri="/tmp/chart.png",
            relevance_score=0.84,
            match_level="exact",
            provider_meta={"chart_topic": "economy", "chart_kind": "causal"},
        ),
    ]

    matched = ranker.match([segment], {1: candidates})

    shortlist = matched[0].candidates
    shortlist_ids = [item.id for item in shortlist]

    assert shortlist_ids[0] == "pexels:1"
    assert "pixabay:3" in shortlist_ids
    assert "data_card:4" in shortlist_ids
    assert "pexels:2" not in shortlist_ids


def test_ranker_prefers_better_semantic_match_over_higher_resolution_fallback():
    ranker = Ranker()
    segment = Segment(id=1, text="心脏骤停的电信号紊乱。", visual_type="stock_video", scene_type="b_roll")

    stronger_semantic = MaterialCandidate(
        id="pixabay:semantic",
        source_type="pixabay",
        media_type="video",
        uri="https://example.com/semantic.mp4",
        relevance_score=0.88,
        match_level="exact",
        width=1920,
        height=1080,
        quality_signals={"resolution_fit": 0.82, "duration_fit": 0.9},
    )
    weaker_4k = MaterialCandidate(
        id="pexels:uhd",
        source_type="pexels",
        media_type="video",
        uri="https://example.com/uhd.mp4",
        relevance_score=0.74,
        match_level="approx",
        width=3840,
        height=2160,
        quality_signals={"resolution_fit": 1.0, "duration_fit": 1.0},
    )

    matched = ranker.match([segment], {1: [weaker_4k, stronger_semantic]})

    assert matched[0].primary is not None
    assert matched[0].primary.id == "pixabay:semantic"
