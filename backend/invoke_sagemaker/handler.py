"""Segment step: contract A (in S3) -> P1's SageMaker Serverless endpoint -> contract B written to S3.

Event:  {"job_id", "job_a_s3_uri", "bucket"}
Return: {"seg_b_s3_uri", "roof_count", "warning"}
Request/response format of the endpoint: ml/serve/README.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError
from jsonschema import Draft202012Validator

from common import s3util

ENDPOINT = os.environ.get("ENDPOINT_NAME", "solarrooftop-seg")
# Serverless cold starts can be slow; Step Functions does the retrying (see pipeline_stack.py).
_runtime = None


def _schema_path() -> Path:
    here = Path(__file__).resolve().parent
    bundled = here / "schemas" / "B.schema.json"
    return bundled if bundled.exists() else here.parents[1] / "contracts" / "schemas" / "B.schema.json"


VALIDATOR = Draft202012Validator(json.loads(_schema_path().read_text(encoding="utf-8")))


class ModelBusy(Exception):
    """Endpoint throttled, not ready, or timed out during a cold start. Step Functions retries this."""


class SegmentationFailed(Exception):
    """The model container rejected the request or returned invalid output. Not retried."""


def runtime():
    global _runtime
    if _runtime is None:
        _runtime = boto3.client("sagemaker-runtime",
                                config=Config(read_timeout=70, connect_timeout=10, retries={"max_attempts": 1}))
    return _runtime


def build_request(job: dict) -> dict:
    return {k: job.get(k) for k in ("job_id", "lat", "lng", "image_bounds", "image_s3_uri", "footprint")}


def invoke(payload: dict) -> dict:
    try:
        resp = runtime().invoke_endpoint(EndpointName=ENDPOINT, ContentType="application/json",
                                         Accept="application/json", Body=json.dumps(payload).encode())
    except ReadTimeoutError as e:
        raise ModelBusy(f"endpoint timed out (cold start?): {e}") from e
    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg = e.response["Error"].get("Message", "")
        if code in ("ThrottlingException", "ModelNotReadyException", "ServiceUnavailable", "InternalFailure"):
            raise ModelBusy(f"{code}: {msg}") from e
        raise SegmentationFailed(f"{code}: {msg}") from e
    return json.loads(resp["Body"].read())


def handler(event, context):
    job = s3util.read_json(event["job_a_s3_uri"])
    seg = invoke(build_request(job))
    errors = sorted(VALIDATOR.iter_errors(seg), key=str)
    if errors:
        raise SegmentationFailed(f"model output is not valid contract B: {errors[0].message}")
    uri = s3util.write_json(event["bucket"], s3util.job_key(event["job_id"], "seg_B.json"), seg)
    roofs = sum(1 for f in seg["features"] if f["properties"]["kind"] == "roof")
    return {"seg_b_s3_uri": uri, "roof_count": roofs, "warning": seg.get("warning", "")}
