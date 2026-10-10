"""Send the contracts/ fixture job to the segmentation service and validate the reply against contract B.

Local server or container:   ml/.venv/bin/python ml/serve/invoke.py --url http://localhost:8080
Deployed SageMaker endpoint: ml/.venv/bin/python ml/serve/invoke.py --endpoint solarrooftop-seg --region ap-south-1
  (endpoint mode needs boto3 + AWS credentials; image is sent inline as base64 unless --s3-uri is given)
"""
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def build_payload(s3_uri: str | None, no_footprint: bool) -> dict:
    job = json.loads((ROOT / "contracts/fixtures/job_A.json").read_text())
    payload = {k: job[k] for k in ("job_id", "lat", "lng", "image_bounds")}
    payload["footprint"] = None if no_footprint else job["footprint"]
    if s3_uri:
        payload["image_s3_uri"] = s3_uri
    else:
        payload["image_b64"] = base64.b64encode((ROOT / "contracts/fixtures/rgb.png").read_bytes()).decode()
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="e.g. http://localhost:8080")
    ap.add_argument("--endpoint", help="SageMaker endpoint name")
    ap.add_argument("--region", default="ap-south-1")
    ap.add_argument("--s3-uri", help="use an image already in S3 instead of sending it inline")
    ap.add_argument("--no-footprint", action="store_true")
    args = ap.parse_args()
    body = json.dumps(build_payload(args.s3_uri, args.no_footprint)).encode()

    t0 = time.time()
    if args.url:
        with urllib.request.urlopen(f"{args.url}/ping", timeout=60) as r:
            assert r.status == 200, "ping failed"
        req = urllib.request.Request(f"{args.url}/invocations", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read())
    elif args.endpoint:
        import boto3
        rt = boto3.client("sagemaker-runtime", region_name=args.region)
        resp = rt.invoke_endpoint(EndpointName=args.endpoint, ContentType="application/json", Body=body)
        result = json.loads(resp["Body"].read())
    else:
        ap.error("give --url or --endpoint")
    elapsed = time.time() - t0

    schema = json.loads((ROOT / "contracts/schemas/B.schema.json").read_text())
    Draft202012Validator(schema).validate(result)
    kinds = [f["properties"].get("class", f["properties"]["kind"]) for f in result["features"]]
    print(f"OK contract B valid | {len(kinds)} features {kinds} | {elapsed:.2f}s round trip"
          + (f" | warning: {result['warning']}" if "warning" in result else ""))


if __name__ == "__main__":
    main()
