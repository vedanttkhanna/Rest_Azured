"""CDK assertion tests: synthesize the app (no AWS access needed) and check cost/safety guardrails."""
from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
from stacks.api_stack import ApiStack  # noqa: E402
from stacks.config import Config  # noqa: E402
from stacks.core_stack import CoreStack  # noqa: E402
from stacks.pipeline_stack import PipelineStack  # noqa: E402

ENV = cdk.Environment(account="123456789012", region="ap-south-1")


def synth(**context) -> dict[str, Template]:
    app = cdk.App(context=context)
    cfg = Config.from_scope(app)
    core = CoreStack(app, "SolarCore", cfg=cfg, env=ENV)
    pipeline = PipelineStack(app, "SolarPipeline", cfg=cfg, core=core, env=ENV)
    api = ApiStack(app, "SolarApi", cfg=cfg, core=core, pipeline=pipeline, env=ENV)
    return {s.stack_name: Template.from_stack(s) for s in (core, pipeline, api)}


@pytest.fixture(scope="module")
def stub_templates():
    return synth(alert_emails="team@example.com,second@example.com")


def test_no_network_resources_that_cost_money_idle(stub_templates):
    for t in stub_templates.values():
        for rtype in ("AWS::EC2::VPC", "AWS::EC2::NatGateway", "AWS::EC2::Instance", "AWS::EC2::EIP"):
            t.resource_count_is(rtype, 0)


def test_no_sagemaker_in_stub_mode(stub_templates):
    stub_templates["SolarPipeline"].resource_count_is("AWS::SageMaker::Endpoint", 0)


def test_log_groups_have_7_day_retention(stub_templates):
    for t in stub_templates.values():
        for lg in t.find_resources("AWS::Logs::LogGroup").values():
            assert lg["Properties"]["RetentionInDays"] == 7
            assert lg["DeletionPolicy"] == "Delete"


def test_every_function_has_an_explicit_log_group(stub_templates):
    for t in stub_templates.values():
        for name, fn in t.find_resources("AWS::Lambda::Function").items():
            if "CustomResource" in name or "AutoDelete" in name:
                continue  # CDK-internal helper functions
            assert "LoggingConfig" in fn["Properties"], name


def test_dynamodb_on_demand_with_gsi(stub_templates):
    core = stub_templates["SolarCore"]
    core.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "Jobs", "BillingMode": "PAY_PER_REQUEST",
        "GlobalSecondaryIndexes": [Match.object_like({"IndexName": "job_id-index"})],
    })
    core.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "Quotas", "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True}})


def test_bucket_private_with_lifecycle(stub_templates):
    stub_templates["SolarCore"].has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "BlockPublicPolicy": True,
                                           "IgnorePublicAcls": True, "RestrictPublicBuckets": True},
        "LifecycleConfiguration": {"Rules": [Match.object_like({"ExpirationInDays": 30, "Prefix": "jobs/"})]},
    })


def test_cognito_lite_with_two_groups(stub_templates):
    core = stub_templates["SolarCore"]
    core.has_resource_properties("AWS::Cognito::UserPool", {"UserPoolTier": "LITE"})
    core.resource_count_is("AWS::Cognito::UserPoolGroup", 2)
    core.has_resource_properties("AWS::Cognito::UserPoolClient", {"GenerateSecret": False})


def test_budget_excludes_credits(stub_templates):
    core = stub_templates["SolarCore"]
    core.has_resource_properties("AWS::Budgets::Budget", {
        "Budget": Match.object_like({"CostTypes": {"IncludeCredit": False, "IncludeRefund": False},
                                     "BudgetLimit": {"Amount": 200, "Unit": "USD"}}),
    })
    budget = next(iter(core.find_resources("AWS::Budgets::Budget").values()))
    thresholds = sorted((n["Notification"]["NotificationType"], n["Notification"]["Threshold"])
                        for n in budget["Properties"]["NotificationsWithSubscribers"])
    assert thresholds == [("ACTUAL", 25), ("ACTUAL", 75), ("ACTUAL", 150), ("FORECASTED", 150)]


def test_no_budget_without_emails():
    templates = synth()
    templates["SolarCore"].resource_count_is("AWS::Budgets::Budget", 0)


def test_http_api_routes_all_need_jwt(stub_templates):
    api = stub_templates["SolarApi"]
    routes = api.find_resources("AWS::ApiGatewayV2::Route")
    keys = sorted(r["Properties"]["RouteKey"] for r in routes.values())
    assert keys == ["GET /jobs", "GET /jobs/{id}", "POST /jobs", "POST /jobs/batch"]
    assert all(r["Properties"]["AuthorizationType"] == "JWT" for r in routes.values())
    api.has_resource_properties("AWS::ApiGatewayV2::Stage", {
        "StageName": "$default", "DefaultRouteSettings": {"ThrottlingRateLimit": 10, "ThrottlingBurstLimit": 20}})


def test_state_machine_has_timeout_and_catch(stub_templates):
    pipe = stub_templates["SolarPipeline"]
    sm = next(iter(pipe.find_resources("AWS::StepFunctions::StateMachine").values()))
    definition = "".join(p if isinstance(p, str) else "<ref>" for p in sm["Properties"]["DefinitionString"]["Fn::Join"][1])
    assert '"TimeoutSeconds":300' in definition
    for state in ("SetFetching", "Fetch", "SetSegmenting", "Segment", "SetSimulating", "Simulate", "Save",
                  "MarkFailed", "MarkNoRoof", "RoofFound?"):
        assert f'"{state}"' in definition, state
    assert '"ErrorEquals":["ModelBusy"]' in definition


def test_segment_real_creates_serverless_endpoint(tmp_path):
    model = tmp_path / "model.tar.gz"
    model.write_bytes(b"not a real model")
    pipe = synth(segment="real", model_tar=str(model))["SolarPipeline"]
    pipe.has_resource_properties("AWS::SageMaker::EndpointConfig", {
        "ProductionVariants": [Match.object_like({
            "ServerlessConfig": {"MemorySizeInMB": 4096, "MaxConcurrency": 2},
            "InstanceType": Match.absent(),
        })],
    })
    pipe.has_resource_properties("AWS::SageMaker::Endpoint", {"EndpointName": "solarrooftop-seg"})


def test_segment_real_without_model_fails(tmp_path):
    with pytest.raises(ValueError, match="model.tar.gz"):
        synth(segment="real", model_tar=str(tmp_path / "missing.tar.gz"))


def test_bad_step_mode_rejected():
    with pytest.raises(ValueError, match="fetch"):
        synth(fetch="maybe")
