"""Deploy-time settings, read from CDK context (infra/cdk.json, overridable with `-c key=value`)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from constructs import Construct

from stacks.packaging import REPO

STEP_MODES = ("stub", "real")


def _list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


@dataclass(frozen=True)
class Config:
    fetch: str            # stub | real (P2 Lambda image from solar/)
    segment: str          # stub | real (P1 SageMaker Serverless endpoint from ml/serve/)
    simulate: str         # stub | real (P2 Lambda image from solar/)
    model_tar: Path       # P1's model.tar.gz (git-ignored), needed when segment=real
    model_version: str
    seg_memory_mb: int
    seg_max_concurrency: int
    web_origins: list[str]
    alert_emails: list[str]
    quota_homeowner: int
    quota_installer: int
    batch_max: int
    places_region: str

    @classmethod
    def from_scope(cls, scope: Construct) -> Config:
        ctx = scope.node.try_get_context
        cfg = cls(
            fetch=str(ctx("fetch") or "stub"),
            segment=str(ctx("segment") or "stub"),
            simulate=str(ctx("simulate") or "stub"),
            model_tar=REPO / str(ctx("model_tar") or "data/models/package/model.tar.gz"),
            model_version=str(ctx("model_version") or "segformer-b2-delhi-fp-v1"),
            seg_memory_mb=int(ctx("seg_memory_mb") or 4096),
            seg_max_concurrency=int(ctx("seg_max_concurrency") or 2),
            web_origins=_list(ctx("web_origins") or "http://localhost:5173"),
            # Team e-mails for budget + failure alerts. Kept out of git: set SOLAR_ALERT_EMAILS or -c alert_emails=a,b
            alert_emails=_list(ctx("alert_emails") or os.environ.get("SOLAR_ALERT_EMAILS", "")),
            quota_homeowner=int(ctx("quota_homeowner") or 20),
            quota_installer=int(ctx("quota_installer") or 100),
            batch_max=int(ctx("batch_max") or 25),
            places_region=str(ctx("places_region") or "ap-south-1"),
        )
        for step in ("fetch", "segment", "simulate"):
            if getattr(cfg, step) not in STEP_MODES:
                raise ValueError(f"context {step} must be one of {STEP_MODES}, got {getattr(cfg, step)!r}")
        return cfg
