"""Pipeline: Step Functions fetch -> segment -> simulate -> save, with each step a stub or the real component.

Execution input (from the api Lambda): {job_id, owner_sub, lat, lng, address, bucket}.
Steps exchange S3 URIs, not documents (Step Functions payload limit is 256 KB). Interface: contracts/README.md.
P2's handlers return A / C inline and write them to jobs/{job_id}/job_A.json and report_C.json; the state machine
discards the inline result and passes those deterministic S3 URIs on.
"""
from __future__ import annotations

from aws_cdk import Aws, CfnOutput, Duration, IgnoreMode, RemovalPolicy, Size, Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3_assets as s3_assets
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from stacks.common import log_group, py_function
from stacks.config import Config
from stacks.core_stack import CoreStack
from stacks.packaging import REPO, python_asset

ENDPOINT_NAME = "solarrooftop-seg"
GOOGLE_KEY_PARAM = "/solarrooftop/google_api_key"  # SecureString, created by infra/scripts/set_google_key.sh
# P2's image builds from the repo root with its own solar/Dockerfile.dockerignore. CDK stages the context using the
# root .dockerignore (P1's: excludes everything but ml/serve), so re-include what solar/Dockerfile copies.
# Docker Desktop's containerd store pushes OCI manifests by default; SageMaker accepts only Docker v2 manifests.
DOCKER_V2_OUTPUT = ["type=docker,oci-mediatypes=false"]
P2_CONTEXT_INCLUDE = ["!solar", "!solar/**", "!contracts", "!contracts/schemas", "!contracts/schemas/**",
                      "solar/.venv*", "solar/tests", "solar/validation", "**/__pycache__"]
J = sfn.JsonPath


class PipelineStack(Stack):
    def __init__(self, scope: Construct, id: str, *, cfg: Config, core: CoreStack, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.cfg, self.core = cfg, core
        bucket = core.bucket

        stub_asset = None
        if "stub" in (cfg.fetch, cfg.segment, cfg.simulate):
            stub_asset = python_asset("stubs", {
                "handler.py": "backend/stubs/handler.py",
                "common": "backend/common",
                **{f"fixtures/{n}": f"contracts/fixtures/{n}"
                   for n in ("job_A.json", "rgb.png", "seg_B.json", "report_C.json", "shade_C.png")},
            })

        def stub(step: str) -> lambda_.Function:
            fn = py_function(self, f"{step.capitalize()}StubFn", asset=stub_asset, handler=f"handler.{step}_handler",
                             timeout_s=30, description=f"STUB {step} step (serves contracts/fixtures)")
            bucket.grant_read_write(fn, "jobs/*")
            return fn

        fetch_fn = self._p2_function("fetch") if cfg.fetch == "real" else stub("fetch")
        segment_fn = self._segment_invoker() if cfg.segment == "real" else stub("segment")
        simulate_fn = self._p2_function("simulate") if cfg.simulate == "real" else stub("simulate")

        save_fn = py_function(
            self, "SaveResultFn",
            asset=python_asset("save_result", {"handler.py": "backend/save_result/handler.py",
                                               "common": "backend/common", "schemas": "contracts/schemas"},
                               requirements="backend/save_result/requirements.txt"),
            handler="handler.handler", environment={"TABLE_NAME": core.jobs_table.table_name},
            description="Validates report C and marks the job done",
        )
        bucket.grant_read(save_fn, "jobs/*")
        core.jobs_table.grant_read_write_data(save_fn)

        self.state_machine = self._state_machine(fetch_fn, segment_fn, simulate_fn, save_fn)

        if cfg.alert_emails:
            alarm = cw.Alarm(
                self, "PipelineFailures",
                metric=self.state_machine.metric_failed(period=Duration.minutes(5), statistic="Sum"),
                threshold=1, evaluation_periods=1,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                alarm_description="A SolarRooftop pipeline execution failed",
            )
            alarm.add_alarm_action(cw_actions.SnsAction(core.alerts_topic))

        CfnOutput(self, "StateMachineArn", value=self.state_machine.state_machine_arn)
        CfnOutput(self, "StepModes", value=f"fetch={cfg.fetch} segment={cfg.segment} simulate={cfg.simulate}")

    # ------------------------------------------------------------------ real components

    def _p2_function(self, step: str) -> lambda_.Function:
        """P2's Lambda container image (solar/Dockerfile, see solar/README.md) with fetch_handler / simulate_handler.
        Both functions use the same image (same asset hash); only the command differs."""
        if not (REPO / "solar" / "Dockerfile").exists():
            raise ValueError(f"{step}=real needs solar/Dockerfile (P2). Deploy with -c {step}=stub until it exists.")
        environment = {
            "JOBS_BUCKET": self.core.bucket.bucket_name,  # switches P2's Store to S3 mode
            "HOME": "/tmp",  # only /tmp is writable in Lambda (library caches, Overture CLI)
        }
        if step == "fetch" and self.cfg.google_key:
            # Only once the parameter exists (set_google_key.sh): P2 fails hard if it is configured but missing.
            environment["GOOGLE_SOLAR_SSM_PARAMETER"] = GOOGLE_KEY_PARAM
        fn = lambda_.DockerImageFunction(
            self, f"{step.capitalize()}Fn",
            code=lambda_.DockerImageCode.from_image_asset(
                str(REPO), file="solar/Dockerfile", cmd=[f"handlers.{step}_handler"],
                platform=ecr_assets.Platform.LINUX_AMD64,
                exclude=P2_CONTEXT_INCLUDE, ignore_mode=IgnoreMode.DOCKER, outputs=DOCKER_V2_OUTPUT),
            architecture=lambda_.Architecture.X86_64,
            memory_size=self.cfg.p2_memory_mb,  # new accounts are capped at 3008 MB until a quota increase
            timeout=Duration.seconds(180),  # live Esri/Overture/PVGIS calls; P2 measured 8-38 s per simulation
            ephemeral_storage_size=Size.mebibytes(2048),
            environment=environment,
            description=f"P2 {step} step",
            log_group=log_group(self, f"{step.capitalize()}FnLogs"),
        )
        self.core.bucket.grant_read_write(fn, "jobs/*")
        self.core.bucket.grant_read_write(fn, "weather/*")  # P2's PVGIS weather cache per 0.05 deg cell
        if "GOOGLE_SOLAR_SSM_PARAMETER" in environment:
            fn.add_to_role_policy(iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:{Aws.REGION}:{Aws.ACCOUNT_ID}:parameter{GOOGLE_KEY_PARAM}"]))
        return fn

    def _segment_invoker(self) -> lambda_.Function:
        """P1's model on a SageMaker Serverless endpoint + the Lambda that calls it."""
        cfg = self.cfg
        if not cfg.model_tar.exists():
            raise ValueError(f"segment=real needs P1's model.tar.gz at {cfg.model_tar} (context model_tar)")
        image = ecr_assets.DockerImageAsset(
            self, "SegImage", directory=str(REPO), file="ml/serve/Dockerfile",
            platform=ecr_assets.Platform.LINUX_AMD64,
            # P1's root .dockerignore whitelists only the sources, so CDK's context staging would drop the Dockerfile.
            exclude=["!ml/serve/Dockerfile"], ignore_mode=IgnoreMode.DOCKER, outputs=DOCKER_V2_OUTPUT)
        model_data = s3_assets.Asset(self, "SegModelData", path=str(cfg.model_tar))

        role = iam.Role(self, "SageMakerRole", assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"))
        image.repository.grant_pull(role)
        model_data.grant_read(role)
        self.core.bucket.grant_read(role, "jobs/*")
        role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
            resources=[f"arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/sagemaker/*"]))
        role.add_to_policy(iam.PolicyStatement(actions=["cloudwatch:PutMetricData"], resources=["*"]))

        model = sagemaker.CfnModel(
            self, "SegModel",
            execution_role_arn=role.role_arn,
            primary_container=sagemaker.CfnModel.ContainerDefinitionProperty(
                image=image.image_uri, model_data_url=model_data.s3_object_url,
                environment={"MODEL_VERSION": cfg.model_version}),
        )
        model.node.add_dependency(role)  # role + its policy must exist before SageMaker checks image access
        endpoint_config = sagemaker.CfnEndpointConfig(
            self, "SegEndpointConfig",
            production_variants=[sagemaker.CfnEndpointConfig.ProductionVariantProperty(
                model_name=model.attr_model_name, variant_name="AllTraffic",
                serverless_config=sagemaker.CfnEndpointConfig.ServerlessConfigProperty(
                    memory_size_in_mb=cfg.seg_memory_mb, max_concurrency=cfg.seg_max_concurrency))],
        )
        endpoint = sagemaker.CfnEndpoint(self, "SegEndpoint", endpoint_name=ENDPOINT_NAME,
                                         endpoint_config_name=endpoint_config.attr_endpoint_config_name)
        # SageMaker would create this log group itself with no expiry; own it so it gets 7 days and is destroyed.
        endpoint.node.add_dependency(logs.LogGroup(
            self, "SegEndpointLogs", log_group_name=f"/aws/sagemaker/Endpoints/{ENDPOINT_NAME}",
            retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY))

        fn = py_function(
            self, "SegmentInvokerFn",
            asset=python_asset("invoke_sagemaker", {"handler.py": "backend/invoke_sagemaker/handler.py",
                                                    "common": "backend/common", "schemas": "contracts/schemas"},
                               requirements="backend/invoke_sagemaker/requirements.txt"),
            handler="handler.handler", timeout_s=90, environment={"ENDPOINT_NAME": ENDPOINT_NAME},
            description="Segment step: calls P1's SageMaker Serverless endpoint",
        )
        fn.node.add_dependency(endpoint)
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:InvokeEndpoint"],
            resources=[f"arn:aws:sagemaker:{Aws.REGION}:{Aws.ACCOUNT_ID}:endpoint/{ENDPOINT_NAME}"]))
        self.core.bucket.grant_read_write(fn, "jobs/*")
        CfnOutput(self, "EndpointName", value=ENDPOINT_NAME)
        return fn

    # ------------------------------------------------------------------ state machine

    def _key(self) -> dict:
        return {"owner_sub": tasks.DynamoAttributeValue.from_string(J.string_at("$.owner_sub")),
                "job_id": tasks.DynamoAttributeValue.from_string(J.string_at("$.job_id"))}

    def _set_status(self, id: str, status: str) -> tasks.DynamoUpdateItem:
        return tasks.DynamoUpdateItem(
            self, id, table=self.core.jobs_table, key=self._key(),
            update_expression="SET #s = :s, #u = :u",
            expression_attribute_names={"#s": "status", "#u": "updated_at"},
            expression_attribute_values={":s": tasks.DynamoAttributeValue.from_string(status),
                                         ":u": tasks.DynamoAttributeValue.from_string(J.string_at("$$.State.EnteredTime"))},
            result_path=J.DISCARD,
        )

    def _invoke(self, id: str, fn: lambda_.IFunction, payload: dict, result: dict | None) -> tasks.LambdaInvoke:
        """Invoke a step Lambda; selected return fields land at $.<id lowercased>, or the result is discarded."""
        return tasks.LambdaInvoke(
            self, id, lambda_function=fn, payload=sfn.TaskInput.from_object(payload),
            result_selector=result, result_path=f"$.{id.lower()}" if result else J.DISCARD,
        )

    def _job_uri(self, id: str, name: str, result_key: str, path: str) -> sfn.Pass:
        """Pass state that sets $.<path>.<result_key> = s3://<bucket>/jobs/<job_id>/<name>."""
        uri = J.format("s3://{}/jobs/{}/" + name, J.string_at("$.bucket"), J.string_at("$.job_id"))
        return sfn.Pass(self, id, parameters={result_key: uri}, result_path=f"$.{path}")

    def _state_machine(self, fetch_fn, segment_fn, simulate_fn, save_fn) -> sfn.StateMachine:
        table = self.core.jobs_table
        bucket_name = J.string_at("$.bucket")
        job_id = J.string_at("$.job_id")

        mark_failed = tasks.DynamoUpdateItem(
            self, "MarkFailed", table=table, key=self._key(),
            update_expression="SET #s = :f, error_type = :t, error_cause = :c, #u = :u",
            expression_attribute_names={"#s": "status", "#u": "updated_at"},
            expression_attribute_values={
                ":f": tasks.DynamoAttributeValue.from_string("failed"),
                ":t": tasks.DynamoAttributeValue.from_string(J.string_at("$.error.Error")),
                ":c": tasks.DynamoAttributeValue.from_string(J.string_at("$.error.Cause")),
                ":u": tasks.DynamoAttributeValue.from_string(J.string_at("$$.State.EnteredTime"))},
            result_path=J.DISCARD,
        ).next(sfn.Fail(self, "Failed", error="PipelineFailed"))

        mark_no_roof = tasks.DynamoUpdateItem(
            self, "MarkNoRoof", table=table, key=self._key(),
            update_expression="SET #s = :f, #e = :e, #u = :u",
            expression_attribute_names={"#s": "status", "#e": "error", "#u": "updated_at"},
            expression_attribute_values={
                ":f": tasks.DynamoAttributeValue.from_string("failed"),
                ":e": tasks.DynamoAttributeValue.from_string(
                    "No roof found at this location. Place the pin on the centre of a rooftop and try again."),
                ":u": tasks.DynamoAttributeValue.from_string(J.string_at("$$.State.EnteredTime"))},
            result_path=J.DISCARD,
        ).next(sfn.Succeed(self, "NoRoofFound", comment="Job failed for the user, but not a system failure (no alarm)"))

        fetch = self._invoke("Fetch", fetch_fn,
                             {"job_id": job_id, "lat": J.number_at("$.lat"), "lng": J.number_at("$.lng"),
                              "address": J.string_at("$.address"), "bucket": bucket_name},
                             None)
        fetched = self._job_uri("JobAUri", "job_A.json", "job_a_s3_uri", "fetch")
        segment = self._invoke("Segment", segment_fn,
                               {"job_id": job_id, "job_a_s3_uri": J.string_at("$.fetch.job_a_s3_uri"),
                                "bucket": bucket_name},
                               {"seg_b_s3_uri": J.string_at("$.Payload.seg_b_s3_uri"),
                                "roof_count": J.number_at("$.Payload.roof_count")})
        # Serverless endpoint: throttled (MaxConcurrency) or cold-starting -> back off and retry.
        segment.add_retry(errors=["ModelBusy"], interval=Duration.seconds(10), max_attempts=4, backoff_rate=2)
        # P2 contract: {"A": uri, "B": uri}; job_id/bucket are used by the stub.
        simulate = self._invoke("Simulate", simulate_fn,
                                {"job_id": job_id, "bucket": bucket_name,
                                 "A": J.string_at("$.fetch.job_a_s3_uri"), "B": J.string_at("$.segment.seg_b_s3_uri")},
                                None)
        simulated = self._job_uri("ReportUri", "report_C.json", "report_s3_uri", "simulate")
        save = self._invoke("Save", save_fn,
                            {"job_id": job_id, "owner_sub": J.string_at("$.owner_sub"),
                             "report_s3_uri": J.string_at("$.simulate.report_s3_uri")},
                            {"status": J.string_at("$.Payload.status")})

        steps = [self._set_status("SetFetching", "fetching"), fetch, fetched,
                 self._set_status("SetSegmenting", "segmenting"), segment]
        tail = [self._set_status("SetSimulating", "simulating"), simulate, simulated, save]
        for state in steps + tail:
            if not isinstance(state, sfn.Pass):
                state.add_catch(mark_failed, errors=["States.ALL"], result_path="$.error")

        tail_chain = sfn.Chain.start(tail[0])
        for state in tail[1:]:
            tail_chain = tail_chain.next(state)
        has_roof = (sfn.Choice(self, "RoofFound?")
                    .when(sfn.Condition.number_equals("$.segment.roof_count", 0), mark_no_roof)
                    .otherwise(tail_chain.next(sfn.Succeed(self, "Done"))))
        chain = sfn.Chain.start(steps[0])
        for state in steps[1:]:
            chain = chain.next(state)
        chain = chain.next(has_roof)

        return sfn.StateMachine(
            self, "Pipeline",
            state_machine_name="solarrooftop-pipeline",
            state_machine_type=sfn.StateMachineType.STANDARD,
            definition_body=sfn.DefinitionBody.from_chainable(chain),
            timeout=Duration.minutes(10),
            logs=sfn.LogOptions(destination=log_group(self, "PipelineLogs"), level=sfn.LogLevel.ERROR),
        )
