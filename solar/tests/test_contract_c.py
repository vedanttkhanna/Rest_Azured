from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, ValidationError
from shapely.geometry import shape
from solar.geo import metric

ROOT=Path(__file__).resolve().parents[2]


def test_generated_fixture_schema_and_consistency():
    schema=json.loads((ROOT/"contracts/schemas/C.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report=json.loads((ROOT/"contracts/fixtures/report_C.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)
    panels=report["panels"]["features"]
    assert len(panels)==report["system"]["panel_count"]
    assert abs(report["system"]["kw_dc"]-len(panels)*report["system"]["panel_wp"]/1000)<1e-6
    assert abs(report["energy"]["annual_kwh"]-sum(report["energy"]["monthly_kwh"]))<0.01
    assert (ROOT/report["heatmap_png_s3_uri"]).is_file()
    polygons=[metric(p["geometry"]) for p in panels]
    for i,p in enumerate(polygons):
        assert p.is_valid and not p.is_empty
        assert all(p.intersection(q).area<1e-6 for q in polygons[i+1:])
    for bad in ({"monthly_kwh":[1]*11},{"annual_kwh":-1},{"shade_loss_pct":101}):
        invalid=copy.deepcopy(report);invalid["energy"].update(bad)
        with pytest.raises(ValidationError):Draft202012Validator(schema).validate(invalid)


def test_fixture_panels_respect_detected_obstacles():
    report=json.loads((ROOT/"contracts/fixtures/report_C.json").read_text())
    seg=json.loads((ROOT/"contracts/fixtures/seg_B.json").read_text())
    buffer=report["assumptions"]["layout"]["obstacle_buffer_m"]
    obstacles=[metric(f["geometry"]).buffer(buffer-1e-6) for f in seg["features"] if f["properties"]["kind"]=="obstacle"]
    for panel in report["panels"]["features"]:
        p=metric(panel["geometry"])
        assert all(p.intersection(o).area<1e-7 for o in obstacles)
