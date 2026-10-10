"""HTTP API (Cognito JWT authorizer) -> api Lambda (Cedar authz, DynamoDB, Location Service, Step Functions)."""
from __future__ import annotations

from aws_cdk import Aws, CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_iam as iam
from constructs import Construct

from stacks.common import py_function
from stacks.config import Config
from stacks.core_stack import CoreStack
from stacks.packaging import python_asset
from stacks.pipeline_stack import PipelineStack


class ApiStack(Stack):
    def __init__(self, scope: Construct, id: str, *, cfg: Config, core: CoreStack, pipeline: PipelineStack,
                 **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        fn = py_function(
            self, "ApiFn",
            asset=python_asset("api", {
                "handler.py": "backend/api/handler.py", "authz.py": "backend/api/authz.py",
                "geocode.py": "backend/api/geocode.py", "quota.py": "backend/api/quota.py",
                "common": "backend/common", "policies": "infra/policies",
            }, requirements="backend/api/requirements.txt"),
            handler="handler.handler",
            timeout_s=29,  # HTTP API integration limit is 30 s
            memory_mb=512,
            environment={
                "TABLE_NAME": core.jobs_table.table_name,
                "QUOTA_TABLE_NAME": core.quota_table.table_name,
                "STATE_MACHINE_ARN": pipeline.state_machine.state_machine_arn,
                "BUCKET": core.bucket.bucket_name,
                "QUOTA_HOMEOWNER": str(cfg.quota_homeowner),
                "QUOTA_INSTALLER": str(cfg.quota_installer),
                "BATCH_MAX": str(cfg.batch_max),
                "PLACES_REGION": cfg.places_region,
            },
            description="SolarRooftop HTTP API",
        )
        core.jobs_table.grant_read_write_data(fn)
        core.quota_table.grant_read_write_data(fn)
        pipeline.state_machine.grant_start_execution(fn)
        core.bucket.grant_read(fn, "jobs/*")  # report JSON + presigned heatmap URLs
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["geo-places:Geocode"],
            resources=[f"arn:aws:geo-places:{cfg.places_region}::provider/default"]))

        api = apigw.HttpApi(
            self, "HttpApi",
            api_name="solarrooftop-api",
            create_default_stage=False,
            cors_preflight=apigw.CorsPreflightOptions(
                allow_origins=cfg.web_origins,
                allow_methods=[apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.OPTIONS],
                allow_headers=["Authorization", "Content-Type"],
                max_age=Duration.hours(1),
            ),
        )
        apigw.HttpStage(self, "DefaultStage", http_api=api, stage_name="$default", auto_deploy=True,
                        throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=20))

        authorizer = authorizers.HttpUserPoolAuthorizer(
            "CognitoAuthorizer", core.user_pool, user_pool_clients=[core.user_pool_client])
        integration = integrations.HttpLambdaIntegration("ApiIntegration", fn)
        for path, methods in (("/jobs", [apigw.HttpMethod.GET, apigw.HttpMethod.POST]),
                              ("/jobs/{id}", [apigw.HttpMethod.GET]),
                              ("/jobs/batch", [apigw.HttpMethod.POST])):
            api.add_routes(path=path, methods=methods, integration=integration, authorizer=authorizer)

        CfnOutput(self, "ApiUrl", value=f"https://{api.api_id}.execute-api.{Aws.REGION}.amazonaws.com")
