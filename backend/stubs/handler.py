"""Stub pipeline steps that serve contracts/fixtures, so the whole pipeline runs before P1/P2 are wired in.

Same event/return shapes as the real steps (see contracts/README.md, "Pipeline step interface"):
  fetch_handler     {job_id, lat, lng, address, bucket}            -> {job_a_s3_uri}
  segment_handler   {job_id, job_a_s3_uri, bucket}                 -> {seg_b_s3_uri, roof_count, warning}
  simulate_handler  {job_id, bucket, A, B}                       -> {report_s3_uri}
The fixture image is one Mayur Vihar building, so stub results always describe that building, whatever was asked.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from common import s3util

DELAY = float(os.environ.get("STUB_DELAY_SECONDS", "2"))  # lets the UI's progress stepper visibly advance


def _fixture_dir() -> Path:
    here = Path(__file__).resolve().parent
    bundled = here / "fixtures"
    return bundled if bundled.is_dir() else here.parents[1] / "contracts" / "fixtures"


FIXTURES = _fixture_dir()


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _copy_file(name: str, bucket: str, job_id: str, content_type: str) -> str:
    key = s3util.job_key(job_id, name)
    s3util.s3().put_object(Bucket=bucket, Key=key, Body=(FIXTURES / name).read_bytes(), ContentType=content_type)
    return f"s3://{bucket}/{key}"


def fetch_handler(event, context):
    time.sleep(DELAY)
    job = _fixture("job_A.json")
    job["job_id"] = event["job_id"]
    job["image_s3_uri"] = _copy_file("rgb.png", event["bucket"], event["job_id"], "image/png")
    job["address"] = event.get("address") or job.get("address")
    return {"job_a_s3_uri": s3util.write_json(event["bucket"], s3util.job_key(event["job_id"], "job_A.json"), job)}


def segment_handler(event, context):
    time.sleep(DELAY)
    seg = _fixture("seg_B.json")
    seg["job_id"] = event["job_id"]
    uri = s3util.write_json(event["bucket"], s3util.job_key(event["job_id"], "seg_B.json"), seg)
    roofs = sum(1 for f in seg["features"] if f["properties"]["kind"] == "roof")
    return {"seg_b_s3_uri": uri, "roof_count": roofs, "warning": seg.get("warning", "")}


def simulate_handler(event, context):
    time.sleep(DELAY)
    report = _fixture("report_C.json")
    report["job_id"] = event["job_id"]
    report["heatmap_png_s3_uri"] = _copy_file("shade_C.png", event["bucket"], event["job_id"], "image/png")
    uri = s3util.write_json(event["bucket"], s3util.job_key(event["job_id"], "report_C.json"), report)
    return {"report_s3_uri": uri}
