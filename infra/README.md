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

Local settings live in the git-ignored repo-root **`.env`** (loaded by every script via
[scripts/env.sh](scripts/env.sh) / [scripts/dotenv.py](scripts/dotenv.py), which also put `aws` and `docker` on PATH):

```
AWS_PROFILE=solar
AWS_REGION=ap-south-1
SOLAR_ALERT_EMAILS=a@x.com,b@y.com
SOLAR_STEP_MODES="fetch=real segment=real simulate=real"
```

```bash
aws login --profile solar                      # when the session has expired
.venv/Scripts/python.exe infra/scripts/check.py  # health check: every part OK/FAIL + one real job + picture
infra/scripts/deploy.sh                        # deploy (step modes from .env; Docker Desktop must be running)
.venv/Scripts/python.exe infra/scripts/smoke.py  # full API test: auth, create, poll, 401/403/404/400/batch
infra/scripts/make_installer.sh someone@example.com
infra/scripts/set_google_key.sh                # P2's Google key -> SSM SecureString /solarrooftop/google_api_key
infra/scripts/teardown.sh                      # after judging: destroy everything + leftovers check
```

Hand-off for the web app: [docs/HANDOFF_P4.md](../docs/HANDOFF_P4.md).

### Website hosting (Amplify)

`SolarCore` creates an Amplify Hosting app `solarrooftop-web` with a `main` branch (no Git connection) and a
single-page-app rewrite rule. Its URL is the stack output `WebUrl` (currently https://main.da6yw5ko9zhmc.amplifyapp.com) and is added
automatically to the API and S3 CORS origins, next to `web_origins` (`http://localhost:5173,http://127.0.0.1:5173`).
Publish the web app after the stacks are deployed, and again after every change in `web/`:

```bash
.venv/Scripts/python.exe infra/scripts/deploy_web.py   # export_env -> npm run build -> zip web/dist -> Amplify deployment
```
Amplify's CDN caches responses (s-maxage 1 year): after changing the Amplify rewrite rules, run `deploy_web.py`
again (a new deployment clears the cache). `check.py` verifies the site and that `.mjs` assets are served as JavaScript.

Local Lambda run with SAM CLI (Docker running), using the synthesized template instead of a separate `template.yaml`:
`sam local invoke -t infra/cdk.out/SolarApi.template.json <ApiFn logical id> -e <event.json>`.

## Gotchas

- **The SPA rewrite rule must list every static file type the build emits.** It first lacked `mjs`, so MapLibre's
  worker (`assets/maplibre-gl-worker-*.mjs`) was answered with `index.html` and hosted maps never finished loading
  (dev mode was unaffected). Test: `test_spa_rewrite_keeps_static_files_including_mjs_workers`.

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
