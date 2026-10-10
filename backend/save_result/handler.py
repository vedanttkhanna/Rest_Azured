"""Save step: check report C, mark the job done in DynamoDB and copy summary numbers for job lists.

Event:  {"job_id", "owner_sub", "report_s3_uri"}
Return: {"status": "done"}
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import boto3
from jsonschema import Draft202012Validator

from common import s3util

TABLE = os.environ.get("TABLE_NAME", "Jobs")
REQUIRED = ("building", "system", "energy", "finance")


def _validator():
    """Full schema check once contracts/schemas/C.schema.json exists (P2 owns it); until then key checks only."""
    here = Path(__file__).resolve().parent
    for p in (here / "schemas" / "C.schema.json", here.parents[1] / "contracts" / "schemas" / "C.schema.json"):
        if p.exists():
            return Draft202012Validator(json.loads(p.read_text(encoding="utf-8")))
    return None


VALIDATOR = _validator()


class InvalidReport(Exception):
    pass


def check_report(report: dict) -> None:
    missing = [k for k in REQUIRED if not isinstance(report.get(k), dict)]
    if missing:
        raise InvalidReport(f"report is missing {missing}")
    if VALIDATOR is not None:
        errors = sorted(VALIDATOR.iter_errors(report), key=str)
        if errors:
            raise InvalidReport(f"report is not valid contract C: {errors[0].message}")


def _num(v):
    return Decimal(str(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def handler(event, context):
    report = s3util.read_json(event["report_s3_uri"])
    check_report(report)
    summary = {
        "kw_dc": _num(report["system"].get("kw_dc")),
        "annual_kwh": _num(report["energy"].get("annual_kwh")),
        "payback_years": _num(report["finance"].get("payback_years")),
    }
    names = {"#s": "status", "#r": "report_s3_uri", "#u": "updated_at"}
    values = {":d": "done", ":r": event["report_s3_uri"],
              ":u": datetime.now(UTC).isoformat(timespec="seconds")}
    sets = ["#s = :d", "#r = :r", "#u = :u"]
    for i, (k, v) in enumerate(summary.items()):
        if v is not None:
            names[f"#k{i}"], values[f":k{i}"] = k, v
            sets.append(f"#k{i} = :k{i}")
    boto3.resource("dynamodb").Table(TABLE).update_item(
        Key={"owner_sub": event["owner_sub"], "job_id": event["job_id"]},
        UpdateExpression="SET " + ", ".join(sets) + " REMOVE #e, error_type, error_cause",
        ExpressionAttributeNames={**names, "#e": "error"},
        ExpressionAttributeValues=values,
    )
    return {"status": "done"}
