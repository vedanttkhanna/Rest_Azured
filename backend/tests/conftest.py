"""Shared fixtures: fake AWS (moto) with the same tables/bucket/state machine the CDK stacks create."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
FIXTURES = REPO / "contracts" / "fixtures"
BUCKET = "solarrooftop-jobs-test"

os.environ.update({
    "AWS_DEFAULT_REGION": "ap-south-1", "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing", "AWS_SESSION_TOKEN": "testing",
    "TABLE_NAME": "Jobs", "QUOTA_TABLE_NAME": "Quotas", "BUCKET": BUCKET, "STUB_DELAY_SECONDS": "0",
})
sys.path.insert(0, str(BACKEND))  # `common` package


def load(rel: str, name: str):
    """Import backend/<rel> under a unique module name (every Lambda's entry file is called handler.py)."""
    path = BACKEND / rel
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def aws():
    with mock_aws():
        ddb = boto3.client("dynamodb")
        ddb.create_table(
            TableName="Jobs", BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("owner_sub", "job_id")],
            KeySchema=[{"AttributeName": "owner_sub", "KeyType": "HASH"}, {"AttributeName": "job_id", "KeyType": "RANGE"}],
            GlobalSecondaryIndexes=[{"IndexName": "job_id-index",
                                     "KeySchema": [{"AttributeName": "job_id", "KeyType": "HASH"}],
                                     "Projection": {"ProjectionType": "ALL"}}],
        )
        ddb.create_table(TableName="Quotas", BillingMode="PAY_PER_REQUEST",
                         AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
                         KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}])
        boto3.client("s3").create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
        sm = boto3.client("stepfunctions").create_state_machine(
            name="solarrooftop-pipeline", roleArn="arn:aws:iam::123456789012:role/sfn",
            definition=json.dumps({"StartAt": "Done", "States": {"Done": {"Type": "Succeed"}}}))
        from common import s3util
        s3util._s3 = None
        yield {"state_machine_arn": sm["stateMachineArn"]}
        s3util._s3 = None


def fixture_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
