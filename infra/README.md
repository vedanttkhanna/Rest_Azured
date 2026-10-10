# infra/ + backend/ (P3)

AWS CDK (Python) app that deploys SolarRooftop AI to `ap-south-1`: three stacks.

| Stack | Contents | Code |
|---|---|---|
| `SolarCore` | S3 jobs bucket (private, 30-day expiry), DynamoDB `Jobs` (+ `job_id-index`) and `Quotas`, Cognito (Lite, groups `Homeowner`/`Installer`, post-confirmation → Homeowner), SNS alerts, $200 budget (credits excluded; alerts $25/$75/$150) | [stacks/core_stack.py](stacks/core_stack.py) |
| `SolarPipeline` | Step Functions: SetFetching → Fetch → SetSegmenting → Segment → RoofFound? → SetSimulating → Simulate → Save; every task catches → `failed` + error; SageMaker Serverless endpoint when `segment=real`; failure alarm | [stacks/pipeline_stack.py](stacks/pipeline_stack.py) |
| `SolarApi` | HTTP API (Cognito JWT on every route, 10 rps throttle, CORS) → api Lambda (Cedar authz, Location Service geocoding, quotas) | [stacks/api_stack.py](stacks/api_stack.py) |

API contract for P4: [contracts/openapi.yaml](../contracts/openapi.yaml). Step event shapes for P1/P2: [contracts/README.md](../contracts/README.md).
Cedar policies: [policies/jobs.cedar](policies/jobs.cedar) + [policies/schema.cedarschema](policies/schema.cedarschema).

## Step modes (stub ↔ real)

Each pipeline step is a stub (serves `contracts/fixtures`) or the real component, chosen with CDK context:

| Context | `stub` (default) | `real` |
|---|---|---|
| `fetch` | `backend/stubs` | P2 Lambda image from `solar/Dockerfile`, `handlers.fetch_handler` |
| `segment` | `backend/stubs` | P1 container `ml/serve/Dockerfile` + `data/models/package/model.tar.gz` on SageMaker Serverless (3072 MB = new-account max, MaxConcurrency 2) + `backend/invoke_sagemaker` |
| `simulate` | `backend/stubs` | P2 Lambda image, `handlers.simulate_handler` |

**Current deployment (2026-10-11): all three real** - `infra/scripts/deploy.sh -c fetch=real -c segment=real -c simulate=real`.
Always pass the same three flags on every deploy; omitting one switches that step back to the stub (and `segment` back to stub deletes the endpoint).
Stub results always describe the fixture building.

Local end-to-end run without AWS or Docker (P2 env + P1 server): see the docstring of [scripts/local_pipeline.py](scripts/local_pipeline.py).

## Setup (Windows 11; also works on Linux/macOS)

Needs: Node 22+, AWS CLI v2, CDK CLI (`npm i -g aws-cdk`), `uv`, Docker Desktop (only for `segment=real` / P2 images
and `sam local`), SAM CLI (optional). From the repo root:

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r infra/requirements-dev.txt     # .venv/bin/python on Linux/macOS
```

Lambda packages are built at synth time **without Docker** ([stacks/packaging.py](stacks/packaging.py)): sources are
copied to `infra/.build/<name>/` and Linux x86_64 wheels are installed with `uv pip install --python-platform`.

## Test (no AWS account needed)

```bash
.venv/Scripts/ruff.exe check backend infra contracts
.venv/Scripts/python.exe -m pytest backend/tests infra/tests contracts/tests -q   # moto + Cedar + CDK assertions
cd infra && PATH="$PWD/../.venv/Scripts:$PATH" cdk synth --quiet
```

## Deploy (P3 only)

One-time: root MFA on, IAM Identity Center admin user → `aws configure sso --profile solar`, then
`cdk bootstrap aws://<account-id>/ap-south-1`.

```bash
export AWS_PROFILE=solar SOLAR_ALERT_EMAILS=p1@x.com,p2@x.com,p3@x.com,p4@x.com
infra/scripts/deploy.sh                 # all stubs; writes web/.env.production and prints the values for P4
python infra/scripts/smoke.py           # end-to-end: auth, create, poll to done, 401/403/404/400 checks
infra/scripts/deploy.sh -c segment=real # P1 endpoint (Docker Desktop must be running)
infra/scripts/make_installer.sh someone@example.com
infra/scripts/set_google_key.sh         # P2's Google key -> SSM SecureString /solarrooftop/google_api_key
infra/scripts/teardown.sh               # after judging: destroy everything + leftovers check
```

Add the Amplify domain to CORS when P4 has it: `-c web_origins=http://localhost:5173,https://main.xxxx.amplifyapp.com`
(also used for the S3 CORS rule on presigned heatmap URLs).

Local Lambda run with SAM CLI (Docker running), using the synthesized template instead of a separate `template.yaml`:
`sam local invoke -t infra/cdk.out/SolarApi.template.json <ApiFn logical id> -e <event.json>`.

## Gotchas

- Budgets must exclude credits (`IncludeCredit: false`) or spend shows as $0 and alerts never fire. Budget data lags up to a day.
- `BUILDX_NO_DEFAULT_ATTESTATIONS=1` (set by `deploy.sh`): Lambda and SageMaker reject images with attestation manifests.
- Cognito group changes only show up in new tokens: sign out/in after `make_installer.sh`.
- SSM SecureStrings can't be created by CloudFormation, hence `set_google_key.sh`.
- Step Functions' overall 5-min timeout skips the Catch; the API reports jobs stuck > 7 min as `failed`.
- No VPC anywhere (a NAT gateway alone is ~$40/month); a CDK test enforces it.
- **New-account quotas:** Lambda memory <= 3008 MB (P2 functions use `p2_memory_mb`=3008), SageMaker serverless memory <= 3072 MB per endpoint. Raise via Service Quotas if needed.
- **SageMaker rejects OCI image manifests**, which Docker Desktop's containerd store produces. `deploy.sh` runs `scripts/prebuild_images.py` after synth to build each image asset as `cdkasset-<id>` with `oci-mediatypes=false`; CDK then only pushes it. (CDK's own `outputs` option crashes CDK CLI 2.1145: `x.replace is not a function`.)
- P1's root `.dockerignore` whitelists only P1's sources; the CDK assets re-include `ml/serve/Dockerfile` and P2's `solar/` + `contracts/schemas/` (test: `test_staged_docker_contexts_contain_their_dockerfiles`).
- Cold start after idle: first job ~2 min (P2 image load ~70 s in fetch, ~35 s in simulate, endpoint ~10 s); warm jobs 16-22 s. Run one job before a demo.
- `deploy.sh` needs Docker Desktop running and `docker` on PATH when any step is `real`.
