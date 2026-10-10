"""Tests for the SageMaker server logic (no Docker needed). Run: ml/.venv/bin/python -m pytest ml/tests -q

Uses the packaged model (data/models/package/model.tar.gz, git-ignored); skipped if it hasn't been built.
"""
from __future__ import annotations

import base64
import importlib
import json
import sys
import tarfile
import time
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/models/package/model.tar.gz"
SCHEMA = json.loads((ROOT / "contracts/schemas/B.schema.json").read_text())
JOB = json.loads((ROOT / "contracts/fixtures/job_A.json").read_text())
IMG_B64 = base64.b64encode((ROOT / "contracts/fixtures/rgb.png").read_bytes()).decode()

pytestmark = pytest.mark.skipif(not PACKAGE.exists(), reason="model.tar.gz not built (ml/serve/package_model.py)")


@pytest.fixture(scope="module")
def serve(tmp_path_factory):
    model_dir = tmp_path_factory.mktemp("opt_ml_model")
    with tarfile.open(PACKAGE) as tar:
        tar.extractall(model_dir, filter="data")
    sys.path.insert(0, str(ROOT / "ml/serve"))
    import os
    os.environ["MODEL_DIR"] = str(model_dir)
    import serve as mod
    mod = importlib.reload(mod)
    t0 = time.time()
    mod.get_model()
    mod.LOAD_SECONDS = time.time() - t0
    return mod


def payload(**overrides):
    p = {k: JOB[k] for k in ("job_id", "lat", "lng", "image_bounds")} | {"footprint": JOB["footprint"],
                                                                          "image_b64": IMG_B64}
    p.update(overrides)
    return p


def test_cold_start_load_time(serve):
    assert serve.LOAD_SECONDS < 30, f"model load took {serve.LOAD_SECONDS:.1f}s"


def test_valid_request_returns_contract_b(serve):
    out = serve.handle(payload())
    Draft202012Validator(SCHEMA).validate(out)
    assert out["job_id"] == JOB["job_id"] and out["features"][0]["properties"]["kind"] == "roof"
    assert "warning" not in out


def test_without_footprint_warns(serve):
    out = serve.handle(payload(footprint=None))
    Draft202012Validator(SCHEMA).validate(out)
    assert "warning" in out


@pytest.mark.parametrize("bad, msg", [
    ({"lat": None}, "missing field: lat"),
    ({"image_b64": None}, "image_s3_uri"),
    ({"image_bounds": [1, 2, 3]}, "image_bounds"),
])
def test_bad_requests_raise_value_error(serve, bad, msg):
    p = payload(**{k: v for k, v in bad.items() if v is not None})
    for k, v in bad.items():
        if v is None:
            p.pop(k)
    with pytest.raises(ValueError, match=msg):
        serve.handle(p)


def test_rejects_wrong_tile_size(serve):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (256, 256)).save(buf, format="PNG")
    with pytest.raises(ValueError, match="512x512"):
        serve.handle(payload(image_b64=base64.b64encode(buf.getvalue()).decode()))
