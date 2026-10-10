"""Contract fixture checks that need no ML dependencies (ml/tests/test_contract_b.py covers B in depth)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parents[1]
FIXTURES = CONTRACTS / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def validator(name):
    return Draft202012Validator(json.loads((CONTRACTS / "schemas" / name).read_text(encoding="utf-8")))


def test_job_a_fixture_matches_schema():
    validator("A.schema.json").validate(load("job_A.json"))


@pytest.mark.parametrize("change", [
    {"image_bounds": [1, 2, 3]},
    {"imagery_source": "drone"},
    {"gsd_m": 0},
    {"lat": 128.6},
])
def test_job_a_schema_rejects_bad_values(change):
    errors = list(validator("A.schema.json").iter_errors(load("job_A.json") | change))
    assert errors


def test_seg_b_fixture_matches_schema():
    validator("B.schema.json").validate(load("seg_B.json"))


def test_fixtures_describe_one_job():
    ids = {load(n)["job_id"] for n in ("job_A.json", "seg_B.json", "report_C.json")}
    assert len(ids) == 1


def test_report_c_draft_is_consistent():
    c = load("report_C.json")
    if (CONTRACTS / "schemas" / "C.schema.json").exists():
        validator("C.schema.json").validate(c)
    assert c["system"]["panel_count"] == len(c["panels"]["features"])
    assert c["system"]["kw_dc"] == pytest.approx(c["system"]["panel_count"] * c["system"]["panel_wp"] / 1000)
    assert sum(c["energy"]["monthly_kwh"]) == c["energy"]["annual_kwh"] and len(c["energy"]["monthly_kwh"]) == 12
    f = c["finance"]
    assert f["net_cost_inr"] == f["capex_inr"] - f["subsidy_inr"]
    assert c["heatmap_bounds"] == load("job_A.json")["image_bounds"]
    assert (FIXTURES / "shade.png").exists()
