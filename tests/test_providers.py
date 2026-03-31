from cmm.config import MatchingSettings
from cmm.fetcher.pexels import _duration_fit as pexels_duration_fit
from cmm.fetcher.pexels import _select_video_file
from cmm.fetcher.pixabay import _duration_fit as pixabay_duration_fit
from cmm.fetcher.pixabay import _select_video_variant


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
