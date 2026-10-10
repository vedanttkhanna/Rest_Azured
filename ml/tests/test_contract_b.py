"""Contract-B tests. Run from repo root: ml/.venv/bin/python -m pytest ml/tests -q

The model-based tests need data/models/segformer_b2_delhi_fp/best (git-ignored) and are skipped without it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from PIL import Image
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "serve"))
import segment  # noqa: E402

SCHEMA = json.loads((ROOT / "contracts/schemas/B.schema.json").read_text())
FIXTURES = ROOT / "contracts/fixtures"
MODEL = ROOT / "data/models/segformer_b2_delhi_fp/best"
TO_UTM = Transformer.from_crs(4326, 32643, always_xy=True).transform


def check_contract_b(fc: dict, bounds: list[float]) -> None:
    Draft202012Validator(SCHEMA).validate(fc)
    tile = box(*bounds).buffer(1e-6)
    roofs = {f["properties"]["id"]: shape(f["geometry"]) for f in fc["features"] if f["properties"]["kind"] == "roof"}
    for f in fc["features"]:
        g = shape(f["geometry"])
        assert g.is_valid and not g.is_empty, f["properties"]["id"]
        ring = f["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1], "ring not closed"
        assert tile.contains(g), "geometry outside tile"
        p = f["properties"]
        if p["kind"] == "obstacle":
            assert p["roof_id"] in roofs
            if p["class"] != "tree":  # trees may overhang the roof edge
                assert roofs[p["roof_id"]].buffer(1e-7).contains(g), f"{p['id']} not on its roof"


def test_fixture_matches_schema():
    fc = json.loads((FIXTURES / "seg_B.json").read_text())
    job = json.loads((FIXTURES / "job_A.json").read_text())
    check_contract_b(fc, job["image_bounds"])
    assert fc["job_id"] == job["job_id"]


def test_schema_rejects_bad_class():
    fc = json.loads((FIXTURES / "seg_B.json").read_text())
    bad = json.loads(json.dumps(fc))
    obstacles = [f for f in bad["features"] if f["properties"]["kind"] == "obstacle"]
    if not obstacles:
        pytest.skip("fixture has no obstacles")
    obstacles[0]["properties"]["class"] = "spaceship"
    with pytest.raises(Exception):
        Draft202012Validator(SCHEMA).validate(bad)


def test_tile_geo_roundtrip():
    geo = segment.TileGeo([77.2931962, 28.603681, 77.2938828, 28.6042839], 512, 512)
    for x, y in [(0, 0), (511, 511), (256, 100)]:
        assert np.allclose(geo.to_px(*geo.to_lonlat(x, y)), (x, y), atol=1e-6)
    assert 0.12 < geo.gsd < 0.14


@pytest.mark.skipif(not MODEL.exists(), reason="trained model not available")
@pytest.mark.parametrize("use_footprint", [True, False])
def test_model_output_on_fixture(use_footprint):
    job = json.loads((FIXTURES / "job_A.json").read_text())
    model, device = segment.load_model(MODEL, "cpu")
    img = np.asarray(Image.open(FIXTURES / "rgb.png").convert("RGB"))
    probs = segment.predict_probs(model, device, img)
    fc = segment.to_contract_b(probs, job["image_bounds"], job["lat"], job["lng"], job["job_id"], "test",
                               job["footprint"] if use_footprint else None, image=img)
    check_contract_b(fc, job["image_bounds"])
    roof = shape(next(f["geometry"] for f in fc["features"] if f["properties"]["kind"] == "roof"))
    area = transform(TO_UTM, roof).area
    fp_area = transform(TO_UTM, shape(job["footprint"])).area
    assert roof.buffer(1e-6).contains(shape({"type": "Point", "coordinates": [job["lng"], job["lat"]]})) or \
        roof.distance(shape({"type": "Point", "coordinates": [job["lng"], job["lat"]]})) < 1e-4
    if use_footprint:
        assert 0.5 * fp_area < area < 2.0 * fp_area, f"roof {area:.0f} m2 vs footprint {fp_area:.0f} m2"
    else:  # documented fallback: capped to a 12 m radius, flagged with a warning when the cap applied
        assert area <= np.pi * 12.0 ** 2 * 1.05, f"roof {area:.0f} m2 exceeds the 12 m cap"
        if area > 2.0 * fp_area:
            assert "warning" in fc


@pytest.mark.skipif(not MODEL.exists(), reason="trained model not available")
def test_no_roof_on_empty_ground():
    model, device = segment.load_model(MODEL, "cpu")
    img = np.full((512, 512, 3), (110, 110, 105), np.uint8)  # featureless asphalt-grey tile
    probs = segment.predict_probs(model, device, img)
    fc = segment.to_contract_b(probs, [77.2931962, 28.603681, 77.2938828, 28.6042839], 28.604, 77.2935, "j", "t",
                               image=img)
    check_contract_b(fc, [77.2931962, 28.603681, 77.2938828, 28.6042839])
    assert fc["features"] == [] and "warning" in fc
