#!/usr/bin/env python3
"""SolarRooftop AI infrastructure. Deploy everything: `cdk deploy --all` from infra/ (see infra/README.md)."""
from __future__ import annotations

import os

import aws_cdk as cdk

from stacks.api_stack import ApiStack
from stacks.config import Config
from stacks.core_stack import CoreStack
from stacks.pipeline_stack import PipelineStack

app = cdk.App()
cfg = Config.from_scope(app)
env = cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region="ap-south-1")

core = CoreStack(app, "SolarCore", cfg=cfg, env=env, description="SolarRooftop AI: storage, auth, budget")
pipeline = PipelineStack(app, "SolarPipeline", cfg=cfg, core=core, env=env,
                         description="SolarRooftop AI: Step Functions pipeline + SageMaker endpoint")
ApiStack(app, "SolarApi", cfg=cfg, core=core, pipeline=pipeline, env=env, description="SolarRooftop AI: HTTP API")

cdk.Tags.of(app).add("project", "solarrooftop")
app.synth()
