from cmm.config import MatchingSettings
from cmm.fetcher.coverr import _candidate_from_coverr_item
from cmm.fetcher.nasa import _best_image_link, _infer_video_dimensions, _pick_video_href
from cmm.fetcher.pexels import _duration_fit as pexels_duration_fit
from cmm.fetcher.pexels import _select_video_file
from cmm.fetcher.pixabay import _duration_fit as pixabay_duration_fit
from cmm.fetcher.pixabay import _select_video_variant
from cmm.models import Segment


def test_pexels_selects_smallest_acceptable_vertical_hd_file():
    matching = MatchingSettings(video_min_resolution=1080, video_orientation="vertical")
    files = [
        {"link": "large.mp4", "width": 1440, "height": 2560},
        {"link": "medium.mp4", "width": 1080, "height": 1920},
        {"link": "horizontal.mp4", "width": 1920, "height": 1080},
    ]

    selected = _select_video_file(files, matching)

    assert selected["link"] == "medium.mp4"


def test_pixabay_selects_smallest_acceptable_vertical_hd_variant():
    matching = MatchingSettings(video_min_resolution=1080, video_orientation="vertical")
    videos = {
        "small": {"url": "small.mp4", "width": 720, "height": 1280},
        "medium": {"url": "medium.mp4", "width": 1080, "height": 1920},
        "large": {"url": "large.mp4", "width": 1440, "height": 2560},
    }

    selected = _select_video_variant(videos, matching)

    assert selected["url"] == "medium.mp4"


def test_duration_fit_prefers_clip_lengths_close_to_segment_hint():
    assert pexels_duration_fit(3.0, 3.0) == 1.0
    assert pexels_duration_fit(3.0, 5.0) == 0.85
    assert pexels_duration_fit(3.0, 12.0) == 0.35
    assert pixabay_duration_fit(3.0, 4.0) == 1.0


def test_pexels_selects_horizontal_asset_when_aspect_is_16_9():
    matching = MatchingSettings(video_min_resolution=1080, video_orientation="horizontal")
    files = [
        {"link": "vertical.mp4", "width": 1080, "height": 1920},
        {"link": "horizontal.mp4", "width": 1920, "height": 1080},
    ]

    selected = _select_video_file(files, matching)

    assert selected["link"] == "horizontal.mp4"


def test_pixabay_prefers_squareish_asset_when_aspect_is_1_1():
    matching = MatchingSettings(video_min_resolution=1080, video_orientation="square")
    videos = {
        "small": {"url": "vertical.mp4", "width": 1080, "height": 1920},
        "medium": {"url": "squareish.mp4", "width": 1080, "height": 1080},
        "large": {"url": "horizontal.mp4", "width": 1920, "height": 1080},
    }

    selected = _select_video_variant(videos, matching)

    assert selected["url"] == "squareish.mp4"


def test_pexels_selects_four_three_asset_when_requested():
    matching = MatchingSettings(video_min_resolution=720, target_aspect="4:3", video_orientation="horizontal")
    files = [
        {"link": "wide.mp4", "width": 1920, "height": 1080},
        {"link": "classic.mp4", "width": 1440, "height": 1080},
    ]

    selected = _select_video_file(files, matching)

    assert selected["link"] == "classic.mp4"


def test_pixabay_selects_three_four_asset_when_requested():
    matching = MatchingSettings(video_min_resolution=720, target_aspect="3:4", video_orientation="vertical")
    videos = {
        "small": {"url": "shorts.mp4", "width": 1080, "height": 1920},
        "medium": {"url": "classic_vertical.mp4", "width": 1080, "height": 1440},
    }

    selected = _select_video_variant(videos, matching)

    assert selected["url"] == "classic_vertical.mp4"


def test_pexels_requires_4k_when_requested():
    matching = MatchingSettings(video_min_resolution=2160, video_orientation="horizontal")
    files = [
        {"link": "fhd.mp4", "width": 1920, "height": 1080},
        {"link": "uhd.mp4", "width": 3840, "height": 2160},
    ]

    selected = _select_video_file(files, matching)

    assert selected["link"] == "uhd.mp4"


def test_pexels_falls_back_to_1080_when_4k_not_available():
    matching = MatchingSettings(video_min_resolution=2160, video_orientation="horizontal")
    files = [
        {"link": "fhd.mp4", "width": 1920, "height": 1080},
        {"link": "hd720.mp4", "width": 1280, "height": 720},
    ]

    selected = _select_video_file(files, matching)

    assert selected["link"] == "fhd.mp4"


def test_pixabay_allows_720_when_requested():
    matching = MatchingSettings(video_min_resolution=720, video_orientation="horizontal")
    videos = {
        "small": {"url": "hd720.mp4", "width": 1280, "height": 720},
        "medium": {"url": "fhd.mp4", "width": 1920, "height": 1080},
    }

    selected = _select_video_variant(videos, matching)

    assert selected["url"] == "hd720.mp4"


def test_pixabay_falls_back_to_720_when_4k_and_1080_absent():
    matching = MatchingSettings(video_min_resolution=2160, video_orientation="horizontal")
    videos = {
        "small": {"url": "hd720.mp4", "width": 1280, "height": 720},
        "medium": {"url": "sd.mp4", "width": 960, "height": 540},
    }

    selected = _select_video_variant(videos, matching)

    assert selected["url"] == "hd720.mp4"


def test_coverr_candidate_maps_video_fields():
    matching = MatchingSettings(video_min_resolution=1080, target_aspect="16:9", video_orientation="horizontal")
    item = {
        "id": "abc",
        "title": "Office workers",
        "thumbnail": "https://example.com/thumb.jpg",
        "poster": "https://example.com/poster.jpg",
        "is_vertical": False,
        "tags": ["office", "business"],
        "aspect_ratio": "16:9",
        "duration": "6.5",
        "max_width": 1920,
        "max_height": 1080,
        "slug": "office-workers-abc",
        "urls": {"mp4": "https://example.com/video.mp4", "mp4_preview": "https://example.com/preview.mp4"},
    }

    candidate = _candidate_from_coverr_item(item, "office", Segment(id=1, text="office"), matching)

    assert candidate is not None
    assert candidate.source_type == "coverr"
    assert candidate.uri == "https://example.com/video.mp4"
    assert candidate.quality_signals["aspect_fit"] == 1.0


def test_nasa_helpers_pick_best_media_links():
    links = [
        {"href": "https://example.com/small.jpg", "rel": "alternate", "render": "image", "width": 640, "height": 360},
        {"href": "https://example.com/orig.jpg", "rel": "canonical", "render": "image", "width": 2000, "height": 1200},
    ]
    hrefs = [
        "http://example.com/file~preview.mp4",
        "http://example.com/file~medium.mp4",
        "http://example.com/file.vtt",
    ]

    assert _best_image_link(links, prefer_canonical=True)["href"] == "https://example.com/orig.jpg"
    assert _pick_video_href(hrefs).endswith("~medium.mp4")
    assert _infer_video_dimensions({"width": 800, "height": 450}) == (1920, 1080)
