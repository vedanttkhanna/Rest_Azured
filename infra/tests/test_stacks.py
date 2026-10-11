"""CDK assertion tests: synthesize the app (no AWS access needed) and check cost/safety guardrails."""
from __future__ import annotations

import json
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
    assert '"TimeoutSeconds":600' in definition
    for state in ("SetFetching", "Fetch", "JobAUri", "SetSegmenting", "Segment", "SetSimulating", "Simulate",
                  "ReportUri", "Save",
                  "MarkFailed", "MarkNoRoof", "RoofFound?"):
        assert f'"{state}"' in definition, state
    assert '"ErrorEquals":["ModelBusy"]' in definition


def test_segment_real_creates_serverless_endpoint(tmp_path):
    model = tmp_path / "model.tar.gz"
    model.write_bytes(b"not a real model")
    pipe = synth(segment="real", model_tar=str(model))["SolarPipeline"]
    pipe.has_resource_properties("AWS::SageMaker::EndpointConfig", {
        "ProductionVariants": [Match.object_like({
            "ServerlessConfig": {"MemorySizeInMB": 3072, "MaxConcurrency": 2},
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


def test_p2_real_uses_one_image_with_s3_mode():
    pipe = synth(fetch="real", simulate="real")["SolarPipeline"]
    fns = {k: v for k, v in pipe.find_resources("AWS::Lambda::Function").items() if v["Properties"].get("PackageType") == "Image"}
    assert len(fns) == 2
    images = {json.dumps(f["Properties"]["Code"]["ImageUri"]) for f in fns.values()}
    assert len(images) == 1  # same asset, different commands
    for f in fns.values():
        env = f["Properties"]["Environment"]["Variables"]
        assert "JOBS_BUCKET" in env and env["HOME"] == "/tmp"
        assert "GOOGLE_SOLAR_SSM_PARAMETER" not in env  # only with -c google_key=true
        assert f["Properties"]["ImageConfig"]["Command"][0] in ("handlers.fetch_handler", "handlers.simulate_handler")


def test_google_key_flag_wires_ssm_parameter():
    pipe = synth(fetch="real", simulate="real", google_key="true")["SolarPipeline"]
    pipe.has_resource_properties("AWS::Lambda::Function", {
        "ImageConfig": {"Command": ["handlers.fetch_handler"]},
        "Environment": {"Variables": Match.object_like({"GOOGLE_SOLAR_SSM_PARAMETER": "/solarrooftop/google_api_key"})},
    })


def test_staged_docker_contexts_contain_their_dockerfiles(tmp_path):
    """CDK stages image contexts through the root .dockerignore; each staged context must keep what its build needs."""
    model = tmp_path / "model.tar.gz"
    model.write_bytes(b"x")
    app = cdk.App(outdir=str(tmp_path / "out"),
                  context={"fetch": "real", "segment": "real", "simulate": "real", "model_tar": str(model)})
    cfg = Config.from_scope(app)
    core = CoreStack(app, "SolarCore", cfg=cfg, env=ENV)
    PipelineStack(app, "SolarPipeline", cfg=cfg, core=core, env=ENV)
    assembly = app.synth()
    manifest = json.loads((Path(assembly.directory) / "SolarPipeline.assets.json").read_text(encoding="utf-8"))
    staged = {d["source"]["dockerFile"]: Path(assembly.directory) / d["source"]["directory"]
              for d in manifest["dockerImages"].values()}
    assert set(staged) == {"ml/serve/Dockerfile", "solar/Dockerfile"}
    for dockerfile, root in staged.items():
        assert (root / dockerfile).is_file(), dockerfile
    p1 = staged["ml/serve/Dockerfile"]
    assert all((p1 / "ml/serve" / f).is_file() for f in ("serve.py", "segment.py", "requirements-serve.txt"))
    p2 = staged["solar/Dockerfile"]
    assert (p2 / "solar/handlers.py").is_file() and (p2 / "solar/requirements.lock.txt").is_file()
    assert (p2 / "contracts/schemas/C.schema.json").is_file()
    assert not (p2 / "solar/tests").exists() and not (p2 / "data").exists()


def test_p2_memory_within_new_account_limit():
    pipe = synth(fetch="real", simulate="real")["SolarPipeline"]
    for f in pipe.find_resources("AWS::Lambda::Function").values():
        assert f["Properties"].get("MemorySize", 128) <= 3008


def test_amplify_app_hosts_spa_and_is_allowed_by_cors(stub_templates):
    core, api = stub_templates["SolarCore"], stub_templates["SolarApi"]
    core.has_resource_properties("AWS::Amplify::App", {
        "Name": "solarrooftop-web", "Platform": "WEB",
        "CustomRules": [Match.object_like({"Target": "/index.html", "Status": "200"})],
    })
    core.has_resource_properties("AWS::Amplify::Branch", {"BranchName": "main", "EnableAutoBuild": False})
    origins = api.find_resources("AWS::ApiGatewayV2::Api")
    allow = next(iter(origins.values()))["Properties"]["CorsConfiguration"]["AllowOrigins"]
    assert "http://localhost:5173" in allow and "http://127.0.0.1:5173" in allow
    assert any("amplifyapp" in json.dumps(o) or "Fn::" in json.dumps(o) for o in allow if not isinstance(o, str))
    bucket = next(iter(core.find_resources("AWS::S3::Bucket").values()))
    bucket_origins = bucket["Properties"]["CorsConfiguration"]["CorsRules"][0]["AllowedOrigins"]
    assert len(bucket_origins) == 3


def test_spa_rewrite_keeps_static_files_including_mjs_workers(stub_templates):
    import re
    app = next(iter(stub_templates["SolarCore"].find_resources("AWS::Amplify::App").values()))
    source = app["Properties"]["CustomRules"][0]["Source"]
    pattern = re.compile(source[2:-2])  # Amplify's regex-rule syntax wraps the regex in </ ... />
    for static in ("/assets/maplibre-gl-worker-VaXr2Fck.mjs", "/assets/index-G2CWcLkS.js", "/sun.svg",
                   "/mockServiceWorker.js", "/assets/app.css", "/demo/shade.png"):
        assert not pattern.search(static), f"{static} would be rewritten to index.html"
    for route in ("/jobs/abc-123", "/history", "/installer", "/assess"):
        assert pattern.search(route), f"{route} must serve index.html"
