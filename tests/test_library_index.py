import json
import os
from pathlib import Path

from PIL import Image

from cmm.library.matcher import LocalLibraryMatcher
from cmm.library.scanner import scan_library
from cmm.models import Segment


def test_scan_library_builds_image_index_and_reuses_cache(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    image_path = root / "cities" / "shanghai_growth.jpg"
    image_path.parent.mkdir()
    Image.new("RGB", (1080, 1920), color="red").save(image_path)
    metadata_path = tmp_path / "metadata.csv"
    metadata_path.write_text(
        "path,title,description,tags,category\n"
        "cities/shanghai_growth.jpg,Shanghai skyline,China economy city growth,china|economy|skyline,city\n",
        encoding="utf-8",
    )
    output_path = root / ".scriptmate-library-index.json"

    first = scan_library(str(root), metadata_path=str(metadata_path), output_path=str(output_path), cache_path=str(output_path))
    second = scan_library(str(root), metadata_path=str(metadata_path), output_path=str(output_path), cache_path=str(output_path))

    assert output_path.exists()
    assert len(first.assets) == 1
    asset = second.assets[0]
    assert asset.relative_path == "cities/shanghai_growth.jpg"
    assert asset.width == 1080
    assert asset.height == 1920
    assert asset.aspect_ratio == "9:16"
    assert asset.orientation == "vertical"
    assert asset.fingerprint
    assert "china" in asset.searchable_text
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["assets"][0]["fingerprint"] == asset.fingerprint

    Image.new("RGB", (1200, 1200), color="blue").save(image_path)
    os.utime(image_path, None)
    updated = scan_library(str(root), metadata_path=str(metadata_path), output_path=str(output_path), cache_path=str(output_path))

    assert updated.assets[0].width == 1200
    assert updated.assets[0].height == 1200
    assert updated.assets[0].aspect_ratio == "1:1"


def test_local_library_matcher_prefers_relevant_aspect_and_metadata(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    city = root / "city.jpg"
    plant = root / "plant.jpg"
    Image.new("RGB", (1080, 1920), color="red").save(city)
    Image.new("RGB", (1920, 1080), color="green").save(plant)
    metadata_path = tmp_path / "metadata.csv"
    metadata_path.write_text(
        "path,title,description,tags,category\n"
        "city.jpg,China city skyline,Shanghai economy growth,china|economy|city,city\n"
        "plant.jpg,Green plant,Leaves and nature,plant|leaf,nature\n",
        encoding="utf-8",
    )
    assets = scan_library(str(root), metadata_path=str(metadata_path)).assets
    segment = Segment(
        id=1,
        text="中国城市经济持续增长。",
        visual_type="stock_image",
        scene_type="infographic",
        search_queries=["china economy city"],
        keywords_en=["china", "economy", "city"],
    )

    matches = LocalLibraryMatcher().match(segment, assets, top_k=2, target_aspect="9:16")

    assert matches[0].provider_meta["title"] == "China city skyline"
    assert matches[0].quality_signals["score_method"] == "local_index"
    assert matches[0].quality_signals["score_breakdown"]["aspect_fit"] > 0
    assert matches[0].quality_signals["local_match_score"] > 0
    assert matches[0].quality_signals["index_fingerprint"]
