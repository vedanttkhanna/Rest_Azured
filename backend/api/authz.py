"""Cedar authorization for the HTTP API. Policies + schema: infra/policies/ (bundled next to this file as policies/)."""
from __future__ import annotations

import os
from pathlib import Path

import cedarpy

KNOWN_GROUPS = ("Homeowner", "Installer")


def _policy_dir() -> Path:
    if os.environ.get("POLICY_DIR"):
        return Path(os.environ["POLICY_DIR"])
    bundled = Path(__file__).resolve().parent / "policies"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[2] / "infra" / "policies"  # running from the repo (tests)


_DIR = _policy_dir()
POLICIES = cedarpy.PolicySet.from_str("\n".join(p.read_text(encoding="utf-8") for p in sorted(_DIR.glob("*.cedar"))))
SCHEMA = cedarpy.Schema.from_str((_DIR / "schema.cedarschema").read_text(encoding="utf-8"))


def parse_groups(claim) -> list[str]:
    """`cognito:groups` arrives as a list, or (HTTP API JWT authorizer) as a string like "[Homeowner Installer]"."""
    if claim is None:
        return []
    if isinstance(claim, str):
        claim = claim.strip("[]").replace(",", " ").split()
    return [g for g in claim if g in KNOWN_GROUPS]


def is_allowed(sub: str, groups: list[str], action: str, resource_type: str, resource_id: str, owner_sub: str) -> bool:
    user = {"type": "User", "id": sub}
    entities = [
        {"uid": user, "attrs": {}, "parents": [{"type": "Group", "id": g} for g in groups]},
        *({"uid": {"type": "Group", "id": g}, "attrs": {}, "parents": []} for g in groups),
        {"uid": {"type": resource_type, "id": resource_id},
         "attrs": {"owner": {"__entity": {"type": "User", "id": owner_sub}}}, "parents": []},
    ]
    if owner_sub != sub:
        entities.append({"uid": {"type": "User", "id": owner_sub}, "attrs": {}, "parents": []})
    request = {"principal": user, "action": {"type": "Action", "id": action},
               "resource": {"type": resource_type, "id": resource_id}, "context": {}}
    result = cedarpy.is_authorized(request, POLICIES, entities, schema=SCHEMA)
    return result.decision == cedarpy.Decision.Allow


def can_on_account(sub: str, groups: list[str], action: str) -> bool:
    return is_allowed(sub, groups, action, "Account", sub, sub)


def can_read_job(sub: str, groups: list[str], job_id: str, owner_sub: str) -> bool:
    return is_allowed(sub, groups, "ReadJob", "Job", job_id, owner_sub)
