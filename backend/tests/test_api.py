"""api Lambda tests against moto: routes, Cedar enforcement, validation, quota, ownership."""
from __future__ import annotations

import json

import boto3
import pytest

from conftest import BUCKET, fixture_json, load

api = load("api/handler.py", "api_handler")


@pytest.fixture
def app(aws, monkeypatch):
    monkeypatch.setattr(api, "STATE_MACHINE_ARN", aws["state_machine_arn"])
    monkeypatch.setattr(api, "_ddb", None)
    monkeypatch.setattr(api, "_sfn", None)
    monkeypatch.setattr(api, "QUOTA_LIMITS", {"Homeowner": 3, "Installer": 10})

    def fake_geocode(address):
        if "nowhere" in address:
            raise api.geocode.GeocodeError(f"address not found: {address!r}")
        if "mumbai" in address.lower():
            return {"lat": 19.07, "lng": 72.87, "label": "Mumbai"}
        return {"lat": 28.6039825, "lng": 77.2935395, "label": f"{address}, Delhi"}

    monkeypatch.setattr(api.geocode, "geocode", fake_geocode)
    return aws


def call(route, *, sub="user-1", groups="[Homeowner]", body=None, job_id=None):
    event = {
        "routeKey": route,
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub, "cognito:groups": groups}}}},
        "body": json.dumps(body) if body is not None else None,
        "pathParameters": {"id": job_id} if job_id else None,
    }
    resp = api.handler(event, None)
    return resp["statusCode"], json.loads(resp["body"])


def jobs_table():
    return boto3.resource("dynamodb").Table("Jobs")


def executions(arn):
    return boto3.client("stepfunctions").list_executions(stateMachineArn=arn)["executions"]


def test_create_with_coordinates_starts_pipeline(app):
    status, body = call("POST /jobs", body={"lat": 28.5921, "lng": 77.046})
    assert status == 201
    item = jobs_table().get_item(Key={"owner_sub": "user-1", "job_id": body["job_id"]})["Item"]
    assert item["status"] == "queued" and item["role"] == "Homeowner"
    runs = executions(app["state_machine_arn"])
    assert [r["name"] for r in runs] == [body["job_id"]]
    started = boto3.client("stepfunctions").describe_execution(executionArn=runs[0]["executionArn"])
    assert json.loads(started["input"]) == {"job_id": body["job_id"], "owner_sub": "user-1", "lat": 28.5921,
                                            "lng": 77.046, "address": None, "bucket": BUCKET}


def test_create_with_address_geocodes(app):
    status, body = call("POST /jobs", body={"address": "Mayur Vihar Phase 1"})
    assert status == 201
    item = jobs_table().get_item(Key={"owner_sub": "user-1", "job_id": body["job_id"]})["Item"]
    assert item["address"] == "Mayur Vihar Phase 1, Delhi"
    assert float(item["lat"]) == pytest.approx(28.6039825)


@pytest.mark.parametrize("body, fragment", [
    ({"lat": 19.07, "lng": 72.87}, "outside the Delhi/NCR"),
    ({"address": "Mumbai Central"}, "outside the Delhi/NCR"),
    ({"address": "nowhere land"}, "address not found"),
    ({}, "give {address} or {lat, lng}"),
    ({"lat": "28.6", "lng": 77.2}, "give {address} or {lat, lng}"),
    ({"lat": True, "lng": 77.2}, "give {address} or {lat, lng}"),
])
def test_create_rejects_bad_input(app, body, fragment):
    status, resp = call("POST /jobs", body=body)
    assert status == 400 and fragment in resp["error"]
    assert executions(app["state_machine_arn"]) == []


def test_create_rejects_non_json(app):
    event = {"routeKey": "POST /jobs", "body": "not json",
             "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "u", "cognito:groups": "[Homeowner]"}}}}}
    assert api.handler(event, None)["statusCode"] == 400


def test_user_without_group_is_forbidden(app):
    status, _ = call("POST /jobs", groups="[]", body={"lat": 28.6, "lng": 77.2})
    assert status == 403


def test_missing_identity_is_401(app):
    resp = api.handler({"routeKey": "GET /jobs", "requestContext": {}}, None)
    assert resp["statusCode"] == 401


def test_unknown_route_is_404(app):
    assert api.handler({"routeKey": "DELETE /jobs"}, None)["statusCode"] == 404


def test_daily_quota(app):
    for _ in range(3):
        assert call("POST /jobs", body={"lat": 28.6, "lng": 77.2})[0] == 201
    status, body = call("POST /jobs", body={"lat": 28.6, "lng": 77.2})
    assert status == 429 and "limit" in body["error"]
    # other users are unaffected
    assert call("POST /jobs", sub="user-2", body={"lat": 28.6, "lng": 77.2})[0] == 201


def test_homeowner_batch_forbidden_by_cedar(app):
    status, body = call("POST /jobs/batch", body={"addresses": ["Dwarka Sector 6"]})
    assert status == 403 and "Installer" in body["error"]


def test_installer_batch(app):
    status, body = call("POST /jobs/batch", sub="inst-1", groups="[Installer]",
                        body={"addresses": ["Dwarka Sector 6", {"lat": 28.7, "lng": 77.1}]})
    assert status == 201 and len(body["job_ids"]) == 2
    assert len(executions(app["state_machine_arn"])) == 2


def test_batch_with_invalid_entry_creates_nothing(app):
    status, body = call("POST /jobs/batch", sub="inst-1", groups="[Installer]",
                        body={"addresses": ["Dwarka Sector 6", "nowhere land", {"lat": 19.0, "lng": 72.8}]})
    assert status == 400
    assert [i["index"] for i in body["invalid"]] == [1, 2]
    assert executions(app["state_machine_arn"]) == []


def test_batch_limits(app, monkeypatch):
    monkeypatch.setattr(api, "BATCH_MAX", 2)
    assert call("POST /jobs/batch", groups="[Installer]", body={"addresses": ["a", "b", "c"]})[0] == 400
    assert call("POST /jobs/batch", groups="[Installer]", body={"addresses": []})[0] == 400
    # quota counts the whole batch at once
    monkeypatch.setattr(api, "QUOTA_LIMITS", {"Homeowner": 3, "Installer": 1})
    assert call("POST /jobs/batch", groups="[Installer]", body={"addresses": ["a", "b"]})[0] == 429


def test_get_own_job_and_not_others(app):
    _, created = call("POST /jobs", body={"lat": 28.6, "lng": 77.2})
    status, body = call("GET /jobs/{id}", job_id=created["job_id"])
    assert status == 200 and body["status"] == "queued" and "report" not in body
    assert call("GET /jobs/{id}", sub="user-2", job_id=created["job_id"])[0] == 404
    assert call("GET /jobs/{id}", sub="user-2", groups="[Installer]", job_id=created["job_id"])[0] == 404
    assert call("GET /jobs/{id}", job_id="no-such-job")[0] == 404


def test_get_done_job_includes_report_and_presigned_heatmap(app):
    _, created = call("POST /jobs", body={"lat": 28.6, "lng": 77.2})
    job_id = created["job_id"]
    report = fixture_json("report_C.json") | {"job_id": job_id,
                                               "heatmap_png_s3_uri": f"s3://{BUCKET}/jobs/{job_id}/shade.png"}
    s3 = boto3.client("s3")
    s3.put_object(Bucket=BUCKET, Key=f"jobs/{job_id}/report_C.json", Body=json.dumps(report))
    jobs_table().update_item(Key={"owner_sub": "user-1", "job_id": job_id},
                             UpdateExpression="SET #s = :d, report_s3_uri = :r",
                             ExpressionAttributeNames={"#s": "status"},
                             ExpressionAttributeValues={":d": "done", ":r": f"s3://{BUCKET}/jobs/{job_id}/report_C.json"})
    status, body = call("GET /jobs/{id}", job_id=job_id)
    assert status == 200 and body["status"] == "done"
    assert body["report"]["system"]["panel_count"] == report["system"]["panel_count"]
    assert body["heatmap_png_url"].startswith(f"https://{BUCKET}.s3.ap-south-1.amazonaws.com/")  # regional host
    assert "shade.png" in body["heatmap_png_url"]


def test_failed_job_shows_error_message(app):
    _, created = call("POST /jobs", body={"lat": 28.6, "lng": 77.2})
    cause = json.dumps({"errorMessage": "PVGIS unreachable", "errorType": "ConnectionError"})
    jobs_table().update_item(Key={"owner_sub": "user-1", "job_id": created["job_id"]},
                             UpdateExpression="SET #s = :f, error_type = :t, error_cause = :c",
                             ExpressionAttributeNames={"#s": "status"},
                             ExpressionAttributeValues={":f": "failed", ":t": "ConnectionError", ":c": cause})
    status, body = call("GET /jobs/{id}", job_id=created["job_id"])
    assert status == 200 and body["error"] == "ConnectionError: PVGIS unreachable"


def test_list_only_my_jobs_newest_first(app):
    ids = [call("POST /jobs", body={"lat": 28.6, "lng": 77.2})[1]["job_id"] for _ in range(2)]
    call("POST /jobs", sub="user-2", body={"lat": 28.6, "lng": 77.2})
    for i, job_id in enumerate(ids):  # make created_at order deterministic
        jobs_table().update_item(Key={"owner_sub": "user-1", "job_id": job_id},
                                 UpdateExpression="SET created_at = :c",
                                 ExpressionAttributeValues={":c": f"2026-10-10T10:0{i}:00+00:00"})
    status, body = call("GET /jobs")
    assert status == 200
    assert [j["job_id"] for j in body["jobs"]] == list(reversed(ids))


def test_pipeline_start_failure_marks_job_failed(app, monkeypatch):
    class Broken:
        def start_execution(self, **kwargs):
            raise RuntimeError("states down")

    monkeypatch.setattr(api, "_sfn", Broken())
    status, _ = call("POST /jobs", body={"lat": 28.6, "lng": 77.2})
    assert status == 500
    items = jobs_table().scan()["Items"]
    assert len(items) == 1 and items[0]["status"] == "failed" and "states down" in items[0]["error"]


def test_stuck_job_reported_as_failed(app):
    _, created = call("POST /jobs", body={"lat": 28.6, "lng": 77.2})
    jobs_table().update_item(Key={"owner_sub": "user-1", "job_id": created["job_id"]},
                             UpdateExpression="SET #s = :s, updated_at = :u",
                             ExpressionAttributeNames={"#s": "status"},
                             ExpressionAttributeValues={":s": "simulating", ":u": "2026-01-01T00:00:00.000Z"})
    status, body = call("GET /jobs/{id}", job_id=created["job_id"])
    assert status == 200 and body["status"] == "failed" and "timed out while simulating" in body["error"]
    assert call("GET /jobs")[1]["jobs"][0]["status"] == "failed"
