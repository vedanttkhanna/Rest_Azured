"""HTTP API (API Gateway HTTP API, payload v2, Cognito JWT authorizer) for SolarRooftop jobs.

Routes (see contracts/openapi.yaml):
  POST /jobs          {address} | {lat, lng}  -> 201 {job_id}
  GET  /jobs/{id}     -> {job_id, status, ..., report?, heatmap_png_url?, error?}
  GET  /jobs          -> {jobs: [...]}
  POST /jobs/batch    {addresses: [str | {address} | {lat, lng}]} -> 201 {job_ids}   (Installer only, Cedar)
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

import authz
import geocode
import quota
from common import s3util

TABLE = os.environ.get("TABLE_NAME", "Jobs")
QUOTA_TABLE = os.environ.get("QUOTA_TABLE_NAME", "Quotas")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")
BUCKET = os.environ.get("BUCKET", "")
QUOTA_LIMITS = {"Homeowner": int(os.environ.get("QUOTA_HOMEOWNER", "20")),
                "Installer": int(os.environ.get("QUOTA_INSTALLER", "100"))}
BATCH_MAX = int(os.environ.get("BATCH_MAX", "25"))
MAX_ADDRESS = 500  # same limit as the web form
# Delhi/NCR demo bounding box: min_lat, min_lng, max_lat, max_lng
BBOX = [float(x) for x in os.environ.get("BBOX", "28.4,76.8,28.9,77.4").split(",")]
PRESIGN_SECONDS = 900
# The state machine times out after 10 min; a timeout skips its Catch, so the job would stay "running" forever.
STALE_AFTER = timedelta(minutes=12)
RUNNING = ("queued", "fetching", "segmenting", "simulating")
LIST_FIELDS = ("job_id", "status", "address", "lat", "lng", "created_at", "updated_at",
               "kw_dc", "annual_kwh", "payback_years")

_ddb = None
_sfn = None


class HttpError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def ddb():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb


def sfn():
    global _sfn
    if _sfn is None:
        _sfn = boto3.client("stepfunctions")
    return _sfn


def _json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def respond(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=_json_default)}


def parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HttpError(400, "body must be JSON") from e
    if not isinstance(body, dict):
        raise HttpError(400, "body must be a JSON object")
    return body


def caller(event: dict) -> tuple[str, list[str]]:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    sub = claims.get("sub")
    if not sub:
        raise HttpError(401, "missing identity")
    return sub, authz.parse_groups(claims.get("cognito:groups"))


def role_of(groups: list[str]) -> str:
    return "Installer" if "Installer" in groups else "Homeowner"


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def resolve_location(item) -> dict:
    """{address} or {lat, lng} (or a bare address string) -> {lat, lng, address}; validated against BBOX."""
    if isinstance(item, str):
        item = {"address": item}
    if not isinstance(item, dict):
        raise HttpError(400, "give {address} or {lat, lng}")
    address = item.get("address")
    if address is not None and (not isinstance(address, str) or len(address) > MAX_ADDRESS):
        raise HttpError(400, f"address must be text of at most {MAX_ADDRESS} characters")
    if is_number(item.get("lat")) and is_number(item.get("lng")):
        loc = {"lat": float(item["lat"]), "lng": float(item["lng"]), "address": address}
    elif isinstance(address, str) and address.strip():
        if len(address.strip()) > geocode.MAX_QUERY:
            raise HttpError(400, f"address is too long to look up (at most {geocode.MAX_QUERY} characters); "
                                 "shorten it or use a map pin")
        try:
            g = geocode.geocode(address.strip())
        except geocode.GeocodeError as e:
            raise HttpError(400, str(e)) from e
        except (ClientError, BotoCoreError) as e:
            raise HttpError(502, "address lookup is unavailable right now; try again or use a map pin") from e
        loc = {"lat": g["lat"], "lng": g["lng"], "address": g["label"]}
    else:
        raise HttpError(400, "give {address} or {lat, lng}")
    min_lat, min_lng, max_lat, max_lng = BBOX
    if not (min_lat <= loc["lat"] <= max_lat and min_lng <= loc["lng"] <= max_lng):
        raise HttpError(400, f"location ({loc['lat']:.5f}, {loc['lng']:.5f}) is outside the Delhi/NCR service area "
                             f"(lat {min_lat}–{max_lat}, lng {min_lng}–{max_lng})")
    return loc


def start_job(sub: str, groups: list[str], loc: dict) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat(timespec="seconds")
    table = ddb().Table(TABLE)
    table.put_item(Item={
        "owner_sub": sub, "job_id": job_id, "status": "queued", "role": role_of(groups),
        "address": loc.get("address"), "lat": Decimal(str(loc["lat"])), "lng": Decimal(str(loc["lng"])),
        "created_at": now, "updated_at": now,
    })
    execution_input = {"job_id": job_id, "owner_sub": sub, "lat": loc["lat"], "lng": loc["lng"],
                       "address": loc.get("address"), "bucket": BUCKET}
    try:
        sfn().start_execution(stateMachineArn=STATE_MACHINE_ARN, name=job_id, input=json.dumps(execution_input))
    except Exception as e:  # noqa: BLE001 - record and surface any start failure
        table.update_item(Key={"owner_sub": sub, "job_id": job_id},
                          UpdateExpression="SET #s = :f, #e = :e",
                          ExpressionAttributeNames={"#s": "status", "#e": "error"},
                          ExpressionAttributeValues={":f": "failed", ":e": f"could not start pipeline: {e}"})
        raise HttpError(500, "could not start the pipeline") from e
    return job_id


def consume_quota(sub: str, groups: list[str], n: int) -> None:
    try:
        quota.consume(ddb().Table(QUOTA_TABLE), sub, n, QUOTA_LIMITS[role_of(groups)])
    except quota.QuotaExceeded as e:
        raise HttpError(429, str(e)) from e


def error_message(item: dict) -> str | None:
    """Friendly error for failed jobs. The state machine stores Step Functions' {Error, Cause}."""
    if item.get("error"):
        return str(item["error"])[:500]
    cause = item.get("error_cause")
    if cause:
        try:
            cause = json.loads(cause).get("errorMessage", cause)
        except (ValueError, AttributeError):
            pass
        return f"{item.get('error_type', 'Error')}: {cause}"[:500]
    return item.get("error_type")


def summarize(item: dict) -> dict:
    """Job fields shown to the user; jobs stuck past STALE_AFTER are reported as failed."""
    job = {k: item[k] for k in LIST_FIELDS if k in item}
    if item.get("status") in RUNNING:
        try:
            last = datetime.fromisoformat(item.get("updated_at") or item.get("created_at", ""))
        except ValueError:
            last = None
        if last is not None and datetime.now(UTC) - last > STALE_AFTER:
            job["status"] = "failed"
            job["error"] = f"timed out while {item['status']}; please try again"
    if item.get("status") == "failed":
        job["error"] = error_message(item)
    return job


def presign(uri: str | None) -> str | None:
    if not uri or not uri.startswith("s3://"):
        return None
    bucket, key = s3util.parse_s3_uri(uri)
    return s3util.s3().generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key},
                                              ExpiresIn=PRESIGN_SECONDS)


# ---------------------------------------------------------------- routes

def create_job(event, sub, groups):
    if not authz.can_on_account(sub, groups, "CreateJob"):
        raise HttpError(403, "not allowed to create jobs")
    loc = resolve_location(parse_body(event))
    consume_quota(sub, groups, 1)
    return respond(201, {"job_id": start_job(sub, groups, loc)})


def create_batch(event, sub, groups):
    if not authz.can_on_account(sub, groups, "BatchCreate"):
        raise HttpError(403, "batch assessments are available to Installer accounts only")
    addresses = parse_body(event).get("addresses")
    if not isinstance(addresses, list) or not addresses:
        raise HttpError(400, "give a non-empty addresses list")
    if len(addresses) > BATCH_MAX:
        raise HttpError(400, f"at most {BATCH_MAX} addresses per batch")
    locs, invalid = [], []
    for i, item in enumerate(addresses):
        try:
            locs.append(resolve_location(item))
        except HttpError as e:
            invalid.append({"index": i, "input": item, "error": e.message})
    if invalid:
        raise HttpError(400, f"{len(invalid)} of {len(addresses)} addresses are invalid; nothing was created",
                        invalid=invalid)
    consume_quota(sub, groups, len(locs))
    return respond(201, {"job_ids": [start_job(sub, groups, loc) for loc in locs]})


def get_job(event, sub, groups):
    job_id = (event.get("pathParameters") or {}).get("id", "")
    items = ddb().Table(TABLE).query(IndexName="job_id-index", KeyConditionExpression=Key("job_id").eq(job_id),
                                     Limit=1).get("Items", [])
    # Unknown job and someone else's job look the same (404), so job ids can't be probed.
    if not items or not authz.can_read_job(sub, groups, job_id, items[0]["owner_sub"]):
        raise HttpError(404, "job not found")
    item = items[0]
    body = summarize(item)
    if item["status"] == "done" and item.get("report_s3_uri"):
        report = s3util.read_json(item["report_s3_uri"])
        body["report"] = report
        body["heatmap_png_url"] = presign(report.get("heatmap_png_s3_uri"))
    return respond(200, body)


def list_jobs(event, sub, groups):
    if not authz.can_on_account(sub, groups, "ListJobs"):
        raise HttpError(403, "not allowed to list jobs")
    table, items, kwargs = ddb().Table(TABLE), [], {"KeyConditionExpression": Key("owner_sub").eq(sub)}
    while True:
        page = table.query(**kwargs)
        items += page.get("Items", [])
        if "LastEvaluatedKey" not in page or len(items) >= 500:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    jobs = [summarize(i) for i in sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)]
    return respond(200, {"jobs": jobs})


ROUTES = {
    "POST /jobs": create_job,
    "POST /jobs/batch": create_batch,
    "GET /jobs/{id}": get_job,
    "GET /jobs": list_jobs,
}


def handler(event, context):
    route = ROUTES.get(event.get("routeKey", ""))
    if route is None:
        return respond(404, {"error": "no such route"})
    try:
        sub, groups = caller(event)
        return route(event, sub, groups)
    except HttpError as e:
        return respond(e.status, {"error": e.message, **e.extra})
