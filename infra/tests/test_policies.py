"""Cedar policy tests: infra/policies/*.cedar against the schema, plus the full allow/deny matrix."""
from __future__ import annotations

import sys
from pathlib import Path

import cedarpy
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "api"))
import authz  # noqa: E402

POLICY_DIR = REPO / "infra" / "policies"
ACCOUNT_ACTIONS = ["CreateJob", "ListJobs", "BatchCreate", "ExportCsv"]


def test_policies_validate_against_schema():
    policies = "\n".join(p.read_text(encoding="utf-8") for p in sorted(POLICY_DIR.glob("*.cedar")))
    result = cedarpy.validate_policies(policies, (POLICY_DIR / "schema.cedarschema").read_text(encoding="utf-8"))
    assert result.validation_passed, [str(e) for e in result.errors]


@pytest.mark.parametrize("groups, allowed", [
    (["Homeowner"], {"CreateJob", "ListJobs"}),
    (["Installer"], {"CreateJob", "ListJobs", "BatchCreate", "ExportCsv"}),
    (["Homeowner", "Installer"], {"CreateJob", "ListJobs", "BatchCreate", "ExportCsv"}),
    ([], set()),
])
def test_account_action_matrix(groups, allowed):
    for action in ACCOUNT_ACTIONS:
        assert authz.can_on_account("user-1", groups, action) == (action in allowed), (groups, action)


def test_homeowner_cannot_batch():
    assert not authz.can_on_account("user-1", ["Homeowner"], "BatchCreate")


@pytest.mark.parametrize("groups", [["Homeowner"], ["Installer"]])
def test_read_own_job_only(groups):
    assert authz.can_read_job("user-1", groups, "job-1", "user-1")
    assert not authz.can_read_job("user-1", groups, "job-1", "user-2")


def test_no_group_reads_nothing():
    assert not authz.can_read_job("user-1", [], "job-1", "user-1")


def test_cannot_act_on_someone_elses_account():
    assert not authz.is_allowed("user-1", ["Installer"], "BatchCreate", "Account", "user-2", "user-2")


@pytest.mark.parametrize("claim, expected", [
    ("[Homeowner Installer]", ["Homeowner", "Installer"]),
    ("[Installer]", ["Installer"]),
    (["Homeowner"], ["Homeowner"]),
    ("[Admin Homeowner]", ["Homeowner"]),  # unknown groups are dropped
    (None, []),
    ("", []),
])
def test_parse_groups(claim, expected):
    assert authz.parse_groups(claim) == expected
