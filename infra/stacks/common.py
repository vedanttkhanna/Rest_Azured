"""Shared construct helpers: every function gets an explicit 7-day log group that is deleted with the stack."""
from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct


def log_group(scope: Construct, id: str) -> logs.LogGroup:
    return logs.LogGroup(scope, id, retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY)


def py_function(scope: Construct, id: str, *, asset: str, handler: str, environment: dict | None = None,
                timeout_s: int = 30, memory_mb: int = 256, description: str = "") -> lambda_.Function:
    return lambda_.Function(
        scope, id,
        runtime=lambda_.Runtime.PYTHON_3_12,
        architecture=lambda_.Architecture.X86_64,
        code=lambda_.Code.from_asset(asset),
        handler=handler,
        environment=environment or {},
        timeout=Duration.seconds(timeout_s),
        memory_size=memory_mb,
        description=description,
        log_group=log_group(scope, f"{id}Logs"),
    )
