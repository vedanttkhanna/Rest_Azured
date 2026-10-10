"""Pipeline step Lambdas: stubs, SageMaker invoker, save_result, post-confirmation."""
from __future__ import annotations

import io
import json

import boto3
import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from jsonschema import Draft202012Validator

from conftest import BUCKET, REPO, fixture_json, load

stubs = load("stubs/handler.py", "stubs_handler")
invoker = load("invoke_sagemaker/handler.py", "invoker_handler")
save = load("save_result/handler.py", "save_handler")
post_confirm = load("post_confirmation/handler.py", "post_confirm_handler")

SCHEMA_A = Draft202012Validator(json.loads((REPO / "contracts/schemas/A.schema.json").read_text(encoding="utf-8")))
SCHEMA_B = Draft202012Validator(json.loads((REPO / "contracts/schemas/B.schema.json").read_text(encoding="utf-8")))


def s3_json(uri):
    bucket, key = uri[5:].split("/", 1)
    return json.loads(boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read())


def test_stub_pipeline_end_to_end(aws):
    job_id = "job-123"
    a = stubs.fetch_handler({"job_id": job_id, "lat": 28.6, "lng": 77.2, "address": "Somewhere", "bucket": BUCKET}, None)
    job = s3_json(a["job_a_s3_uri"])
    SCHEMA_A.validate(job)
    assert job["job_id"] == job_id and job["address"] == "Somewhere"
    assert job["image_s3_uri"] == f"s3://{BUCKET}/jobs/{job_id}/rgb.png"

    b = stubs.segment_handler({"job_id": job_id, "job_a_s3_uri": a["job_a_s3_uri"], "bucket": BUCKET}, None)
    assert b["roof_count"] == 1
    SCHEMA_B.validate(s3_json(b["seg_b_s3_uri"]))

    c = stubs.simulate_handler({"job_id": job_id, **a, **b, "bucket": BUCKET}, None)
    report = s3_json(c["report_s3_uri"])
    assert report["job_id"] == job_id
    assert report["heatmap_png_s3_uri"] == f"s3://{BUCKET}/jobs/{job_id}/shade.png"
    head = boto3.client("s3").head_object(Bucket=BUCKET, Key=f"jobs/{job_id}/shade.png")
    assert head["ContentType"] == "image/png"


# ------------------------------------------------------------------ SageMaker invoker

class FakeRuntime:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def invoke_endpoint(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"Body": io.BytesIO(json.dumps(self.result).encode())}


def put_job_a(job_id="job-9") -> str:
    job = fixture_json("job_A.json") | {"job_id": job_id, "image_s3_uri": f"s3://{BUCKET}/jobs/{job_id}/rgb.png"}
    boto3.client("s3").put_object(Bucket=BUCKET, Key=f"jobs/{job_id}/job_A.json", Body=json.dumps(job))
    return f"s3://{BUCKET}/jobs/{job_id}/job_A.json"


def client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "InvokeEndpoint")


def test_invoker_sends_p1_request_and_stores_b(aws, monkeypatch):
    seg = fixture_json("seg_B.json") | {"job_id": "job-9"}
    fake = FakeRuntime(result=seg)
    monkeypatch.setattr(invoker, "_runtime", fake)
    out = invoker.handler({"job_id": "job-9", "job_a_s3_uri": put_job_a(), "bucket": BUCKET}, None)
    sent = json.loads(fake.calls[0]["Body"])
    assert set(sent) == {"job_id", "lat", "lng", "image_bounds", "image_s3_uri", "footprint"}
    assert sent["image_s3_uri"] == f"s3://{BUCKET}/jobs/job-9/rgb.png"
    assert out["roof_count"] == 1 and out["warning"] == ""
    assert s3_json(out["seg_b_s3_uri"])["job_id"] == "job-9"


def test_invoker_reports_no_roof(aws, monkeypatch):
    seg = {"job_id": "job-9", "model_version": "v", "type": "FeatureCollection", "features": [],
           "warning": "no roof found at the job point"}
    monkeypatch.setattr(invoker, "_runtime", FakeRuntime(result=seg))
    out = invoker.handler({"job_id": "job-9", "job_a_s3_uri": put_job_a(), "bucket": BUCKET}, None)
    assert out["roof_count"] == 0 and "no roof" in out["warning"]


@pytest.mark.parametrize("error, expected", [
    (client_error("ThrottlingException"), invoker.ModelBusy),
    (client_error("ModelNotReadyException"), invoker.ModelBusy),
    (ReadTimeoutError(endpoint_url="https://x"), invoker.ModelBusy),
    (client_error("ModelError"), invoker.SegmentationFailed),
    (client_error("ValidationError"), invoker.SegmentationFailed),
])
def test_invoker_error_mapping(aws, monkeypatch, error, expected):
    monkeypatch.setattr(invoker, "_runtime", FakeRuntime(error=error))
    with pytest.raises(expected):
        invoker.handler({"job_id": "job-9", "job_a_s3_uri": put_job_a(), "bucket": BUCKET}, None)


def test_invoker_rejects_invalid_model_output(aws, monkeypatch):
    monkeypatch.setattr(invoker, "_runtime", FakeRuntime(result={"job_id": "job-9", "features": "nope"}))
    with pytest.raises(invoker.SegmentationFailed, match="contract B"):
        invoker.handler({"job_id": "job-9", "job_a_s3_uri": put_job_a(), "bucket": BUCKET}, None)


# ------------------------------------------------------------------ save_result

def test_save_marks_done_with_summary(aws):
    table = boto3.resource("dynamodb").Table("Jobs")
    table.put_item(Item={"owner_sub": "u1", "job_id": "j1", "status": "simulating", "error": "old"})
    report = fixture_json("report_C.json") | {"job_id": "j1"}
    boto3.client("s3").put_object(Bucket=BUCKET, Key="jobs/j1/report_C.json", Body=json.dumps(report))
    save.handler({"job_id": "j1", "owner_sub": "u1", "report_s3_uri": f"s3://{BUCKET}/jobs/j1/report_C.json"}, None)
    item = table.get_item(Key={"owner_sub": "u1", "job_id": "j1"})["Item"]
    assert item["status"] == "done" and "error" not in item
    assert float(item["kw_dc"]) == report["system"]["kw_dc"]
    assert float(item["annual_kwh"]) == report["energy"]["annual_kwh"]
    assert float(item["payback_years"]) == report["finance"]["payback_years"]


def test_save_rejects_incomplete_report(aws):
    boto3.client("s3").put_object(Bucket=BUCKET, Key="jobs/j2/report_C.json", Body=json.dumps({"job_id": "j2"}))
    with pytest.raises(save.InvalidReport):
        save.handler({"job_id": "j2", "owner_sub": "u1", "report_s3_uri": f"s3://{BUCKET}/jobs/j2/report_C.json"}, None)


# ------------------------------------------------------------------ post-confirmation

def test_post_confirmation_adds_homeowner(aws):
    idp = boto3.client("cognito-idp")
    pool = idp.create_user_pool(PoolName="p")["UserPool"]["Id"]
    idp.create_group(UserPoolId=pool, GroupName="Homeowner")
    idp.admin_create_user(UserPoolId=pool, Username="alice")
    event = {"triggerSource": "PostConfirmation_ConfirmSignUp", "userPoolId": pool, "userName": "alice"}
    assert post_confirm.handler(event, None) == event
    groups = idp.admin_list_groups_for_user(UserPoolId=pool, Username="alice")["Groups"]
    assert [g["GroupName"] for g in groups] == ["Homeowner"]


def test_post_confirmation_ignores_forgot_password(aws):
    event = {"triggerSource": "PostConfirmation_ConfirmForgotPassword", "userPoolId": "x", "userName": "a"}
    assert post_confirm.handler(event, None) == event
