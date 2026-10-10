"""Small S3 helpers shared by the backend Lambdas (copied into each Lambda package as `common/`)."""
from __future__ import annotations

import json

import boto3
from botocore.config import Config

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        # Explicit virtual addressing makes presigned URLs use the regional host (bucket.s3.<region>.amazonaws.com);
        # the default global host gives SignatureDoesNotMatch for ap-south-1 buckets.
        _s3 = boto3.client("s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    return _s3


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://") or "/" not in uri[5:]:
        raise ValueError(f"not an s3://bucket/key URI: {uri!r}")
    bucket, key = uri[5:].split("/", 1)
    return bucket, key


def read_json(uri: str) -> dict:
    bucket, key = parse_s3_uri(uri)
    return json.loads(s3().get_object(Bucket=bucket, Key=key)["Body"].read())


def write_json(bucket: str, key: str, doc: dict) -> str:
    s3().put_object(Bucket=bucket, Key=key, Body=json.dumps(doc).encode(), ContentType="application/json")
    return f"s3://{bucket}/{key}"


def job_key(job_id: str, name: str) -> str:
    return f"jobs/{job_id}/{name}"
