# TASKS.md — current progress & handoff log

Temporary progress only. Durable facts go to `PROJECT_CONTEXT.md`. Newest handoff entry on top.

## Current objective

Implement P2 only: local solar/geospatial engine and handoff artifacts. Complete live provider/field validation when execution access and credentials are available. P1/P3/P4 implementation is outside this task.

## Status

### Done
- [x] Research + architecture plan; 4 role briefs written (`P1_…`–`P4_….md`).
- [x] P1 Step 2: RID downloaded (`data/raw/RID_m1655470`) and converted to our classes (`data/processed/rid_ours`, fold 1: 1374 train / 352 val / 154 test). Visually checked on 2 previews.
- [x] Shared agent context system: `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`, `CLAUDE.md`, `.agents/rules/shared-context.md`.
- [x] P3 M0/M1/M2 **code** (branch `p3`): `contracts/schemas/A.schema.json`, `contracts/openapi.yaml`, DRAFT `contracts/fixtures/report_C.json` + `shade.png`; CDK app `infra/` (SolarCore / SolarPipeline / SolarApi), backend Lambdas `backend/` (api with Cedar + quota + bbox + batch, SageMaker invoker, save_result, post-confirmation, stubs), Cedar policies, scripts (deploy/smoke/teardown/export_env/make_installer/set_google_key), CI workflow. 74 tests pass. **Nothing deployed to AWS yet.**

### In progress
- [x] P2 local fetch/simulate implementation, report C schema/fixture, heatmap, container recipe, CLI and documentation.
- [x] P2 Python 3.12 local tests: 57 passed; final UTF-8 fetch fix additionally verified by 14 passing fetch tests. Real PVGIS fixture simulation about 15.9 seconds with cached weather.
- [x] P2 live Esri/Overture fetch; 20/20 PVGIS yield comparisons within ±7%; unchanged P1 model -> P2 validation produced 19 reports from 20 attempted buildings (one no-roof rejection).
- [x] P2 Linux Python 3.12 dependency wheel availability: all 37 pinned packages installed for x86_64-manylinux_2_34.
- [ ] P2 remaining verification: Google coverage/DSM (credentials absent), authenticated Earth Engine export, independent surveyed-building accuracy, Docker/Lambda runtime and P4 consumer integration. Linux wheel availability is not a container-runtime test.
- [ ] P1 Stage A training on RID: **stopped at epoch 11/15** (process killed externally ~11:13, no error in log). Best checkpoint epoch 8 kept at `data/models/segformer_b2_rid/best` (val mIoU 0.608). No `last/` checkpoint. Not evaluated on the RID test split yet.
- [x] P1 Stage B fine-tune on footprint auto-labels → `data/models/segformer_b2_delhi_fp/best` (epoch 10 of 12). **Current best model.**
- [x] P1 item 1: post-processing → contract B (`ml/serve/segment.py`), schema `contracts/schemas/B.schema.json`, real fixtures `contracts/fixtures/{job_A.json,rgb.png,seg_B.json}`, tests `ml/tests/test_contract_b.py` (6 passing).
- [x] P1 item 2: SageMaker BYOC package in `ml/serve/` (server, Dockerfile, model.tar.gz builder, invoke client, README for P3). Server verified locally; **Docker image build and AWS deploy not done/verified** (no Docker/Finch/AWS CLI on P1 machine).
- [ ] P1 next: (3) model card + metrics slide; (4) optional quality work (obstacle recall e.g. stair rooms, tree class). `model.tar.gz` **received by P3** (sha256 verified, see Verification).
- [x] P3 M1 **deployed** 2026-10-11 (all steps stubbed), account 336881700677, ap-south-1. API `https://0cw3tjdvo2.execute-api.ap-south-1.amazonaws.com`, user pool `ap-south-1_TDZMa24oN`, client `3l16lr73pip6o9sbbnk258vbb7` (values in `web/.env.production`, git-ignored). smoke.py ALL PASSED.
- [x] **P1 + P2 + P3 combined and deployed (2026-10-11)**: branch `p3` = P3 work + merge of `origin/p1` (P1 + P2) + integration fixes. AWS runs all three real steps (`fetch=real segment=real simulate=real`); SageMaker Serverless endpoint `solarrooftop-seg`. smoke.py ALL PASSED. **Not pushed** (team works on shared branch `p1`; pushing needs user authorization).

### Blockers
- Google Solar coverage/DSM needs credentials (local env or SSM `/solarrooftop/google_api_key` via `infra/scripts/set_google_key.sh`); none supplied yet, so fetch uses Esri. Optional Earth Engine export needs project/service credentials.
- Docker Desktop is installed on the P3 machine but not started yet; needed to build P1's SageMaker image and P2's Lambda image.
- Independent measured roof areas and shading observations are unavailable. Model/footprint agreement is not survey accuracy; real-building validation exposed P1 under-detection and merged roofs.
- Team approval needed (contract PR): schema A, pipeline step interface (contracts/README.md), `heatmap_png_url` in GET /jobs/{id}; P3/P4 review of C (nullable payback).

### Next steps (priority order)
1. ~~P3 first deploy~~ done 2026-10-11 (see Status). Remaining from this item: send `web/.env.production` values to P4; teammates confirm SNS alert subscriptions. Original instructions: user signs in (`aws configure sso --profile solar`, see `infra/README.md`), checks Billing → account plan, `cdk bootstrap aws://<acct>/ap-south-1`, then `SOLAR_ALERT_EMAILS=... infra/scripts/deploy.sh` (all stubs) and `python infra/scripts/smoke.py`; send `web/.env.production` values to P4.
1b. P3: start Docker Desktop, build + run P1's container locally (`ml/serve/README.md` step 3), then `deploy.sh -c segment=real` and `ml/serve/invoke.py --endpoint solarrooftop-seg`. If SageMaker is refused on the Free plan → upgrade to Paid plan (credits still apply).
1c. Contracts: P2 writes `schemas/C.schema.json` and replaces the DRAFT `fixtures/report_C.json`; team approves P3's contract additions (see Blockers).
2. ~~git init~~ done by user 2026-10-10: remote `origin` = https://github.com/vedanttkhanna/Rest_Azured, P1 work on branch `p1`.
3. P2: Google Solar coverage check on ~10 Delhi addresses → record in `solar/docs/coverage_delhi.md`.
4. P3: after deploy — CloudWatch dashboard, architecture diagram (`docs/`), cost log updates, P2 integration (`-c fetch=real -c simulate=real`).
5. P4: `web/` scaffold with MSW mocks from fixtures.
6. P1: labelling guide + CVAT/Roboflow project; SAM 2 baseline.

### Verification results
- **Combined (2026-10-11, P3 machine):** `solar/.venv312/Scripts/python.exe -m pytest solar/tests -q` -> 57 passed; `ml/.venv/Scripts/python.exe -m pytest ml/tests -q` -> 13 passed; P3 suites (infra, backend, contracts) passed. Local end-to-end `infra/scripts/local_pipeline.py` (P2 fetch -> P1 HTTP server -> P2 simulate, A/B/C schema-valid): Mayur Vihar fixture 31 panels / 28,235 kWh; Dwarka Sector 10 11 panels / 10,101 kWh; Lajpat Nagar 27 panels / 24,167 kWh (overlay checked visually); locality centre points (Rohini, Janakpuri) correctly stop with no roof. Containers: P1 image built (1.98 GB) and served /ping + invocations incl. P2's TIFF; P2 image simulate via Lambda RIE matched P2's fixture (30 panels, 27,273.75 kWh); fetch via RIE with `--read-only` + tmpfs /tmp OK (~6 s). **AWS (all real):** `invoke.py --endpoint` 12.3 s cold / 3.8 s warm; smoke.py ALL PASSED (first job 122 s cold: Fetch 76 s, Segment 7.6 s, Simulate 36 s); warm jobs via API 16-22 s with numbers identical to local runs; address job (Mayur Vihar) geocoded to a nearby smaller building (61 m2, 4 panels).
- **P3 live (2026-10-11):** `deploy.sh` (stubs) created SolarCore/SolarPipeline/SolarApi. `python infra/scripts/smoke.py` → **ALL PASSED** (401 no token; job fetching→segmenting→simulating→done in 18 s; report present; presigned heatmap downloads; other user's job 404; list; outside Delhi 400; Homeowner batch 403 via Cedar; Installer batch 201). `smoke.py --address "Pocket A, Mayur Vihar Phase 1, Delhi"` → done in 10 s (Location Service geo-places works in ap-south-1). Fixes found while deploying: (1) `aws login` credentials need `botocore[crt]` (added to requirements-dev); (2) presigned URLs signed for the global S3 host gave `SignatureDoesNotMatch` → `backend/common/s3util.py` now uses virtual addressing (regional host); redeployed SolarPipeline+SolarApi with `--exclusively`.
- **P3 (2026-10-10, Windows 11, Python 3.12.14 via uv):** `.venv/Scripts/python.exe -m pytest backend/tests infra/tests contracts/tests -q` → **74 passed** (api routes/Cedar/quota/bbox/batch/ownership/stale jobs with moto; stubs end-to-end; invoker error mapping; save_result; post-confirmation; Cedar matrix + schema validation; CDK assertions: no VPC/NAT/EC2, 7-day log retention, Lite Cognito, budget excludes credits, JWT on all 4 routes, ServerlessConfig 4096/2). `ruff check backend infra contracts` → clean. `cdk synth` (stub mode and `-c segment=real`) → OK. Lambda package contains the Linux cedarpy binary (`_internal.cpython-312-x86_64-linux-gnu.so`). `model.tar.gz` from P1: sha256 `c345069342ba4ba71ecd074786e8c2e7a4d22004d106b192840f18b895f3a1ea` (matches P1's prefix). **Not run:** any AWS deploy, smoke.py, Docker build of P1/P2 images, `sam local`.
- `ml/train/train.py` smoke test (1 epoch, 200 train / 50 val images): ran OK in 1.75 min; val mIoU 0.340, roof IoU 0.625, obstacles mIoU 0.081 (meaningless this early; only proves the pipeline works).
- `ml/data/download_delhi_tiles.py`: 72 tiles (8 areas × 3×3) downloaded OK; some Dwarka/Rohini centre tiles are roads/parks.
- Labelling pipeline (2026-10-10): `make_label_batch.py` → 49 tiles (39 train / 10 test, test = mayur_vihar), 1,800 pre-label polygons. Round trip pre-labels → `cvat_to_masks.py` vs. original predictions: pixel agreement 0.989; IoU roof 0.963, pv 0.894, tree 0.877, obstacle 0.920. RLE decode (compressed + uncompressed) unit check passed. Stage B smoke test (`train.py --init …rid/best`, 1 epoch on round-trip data, 33 train / 6 val): ran OK, val mIoU 0.694 (on pseudo-labels, not meaningful as accuracy).
- **SageMaker server (2026-10-10, local, no Docker):** `package_model.py` → `data/models/package/model.tar.gz` 101.6 MB, sha256 c345069342ba4ba7…, loads on CPU. `serve.py serve` with unpacked package: /ping 200; `invoke.py` fixture → valid contract B, 0.78–0.82 s round trip; 2 concurrent ~1.3 s each; bad JSON / missing fields / no image → 400; RSS ~1.5 GB; imports 1.4 s + weights <0.1 s. `pytest ml/tests` → **13 passed** (adds 7 server tests).
- **Contract B (2026-10-10):** `ml/.venv/bin/python -m pytest ml/tests -q` → **6 passed** (schema valid on fixture; schema rejects bad class; TileGeo round trip; model output on fixture with and without footprint; empty tile → no roof + warning). Inference 0.19–0.53 s per 512 px tile (MPS / CPU on M5), post-processing ≤0.01 s.
- **Stage B result (2026-10-10), 25 Mayur Vihar test tiles vs footprint labels: roof IoU 0.299 → 0.547**, background 0.783 → 0.798, pixel acc 0.803 → 0.834. **RID val unchanged (no forgetting):** roof 0.794 → 0.800, PV 0.708 → 0.696, obstacle 0.411 → 0.419, tree 0.172 → 0.171. Visual (`data/predictions/before_after_delhi.png`): far more Delhi roofs found; new failure mode = blobby masks that sometimes merge across narrow lanes.
- Footprint labels (`ml/data/footprint_labels.py`, Overture buildings): 8 areas downloaded (56–458 footprints each). Model-based shift alignment tested and **rejected** (best shifts ran to search limit; scores didn't separate good from bad tiles). Visual review → excluded `sangam_vihar` (incomplete footprints) and `okhla` (duplicated/rotated boxes). Result `data/processed/delhi_fp`: 107 train / 18 val / 25 test (mayur_vihar). Mixed set `data/processed/delhi_fp_mix` = Delhi + 300 RID train images (symlinks).
- **Delhi baseline (RID-only model) on footprint test (25 mayur_vihar tiles): roof IoU 0.299**, background 0.783, pixel acc 0.803. Obstacle/PV scores on this set are circular (labels copied from this model inside footprints) — ignore them.
- **RID Stage A (val, fold 1, best = epoch 8):** mIoU 0.608, roof 0.794, existing_pv 0.708, other_obstacle 0.411, tree 0.172, background 0.957, pixel acc 0.949. Epochs 8–10 flat (0.608 / 0.603 / 0.604).
- `ml/infer/predict.py` on 72 Delhi tiles: ran OK → `data/predictions/delhi_rid_only/`. Visual review of 4 tiles: Mayur Vihar roofs mostly found; Sangam Vihar patchy; Lajpat Nagar light flat roofs mostly missed; Okhla finds some existing PV but misses dark PV arrays. No Delhi ground truth, so no Delhi metric.
- `ml/data/rid_to_ours.py`: synthetic-mask test passed; full run on real RID succeeded (1880/1880 images, 2m10s on Mac CPU, 645 MB output). Previews `100`, `1003` visually correct. No committed test suite yet.

---

## Handoff log

### 2026-10-11 — Claude Code — combine P1 + P2 + P3 and deploy all-real
- **Git (local only, nothing pushed):** committed P3 work on `p3` (787e153); merged `origin/p1` (P1 + P2) as e76e230. Conflicts: `report_C.json` -> P2's version (P3 draft + `shade.png` removed); PROJECT_CONTEXT/TASKS -> both sides kept. Then integration commits (see `git log`).
- **Integration changes (P3 files):** `infra/stacks/pipeline_stack.py`: P2 image from repo root via `solar/Dockerfile` (re-include `solar/` past P1's root `.dockerignore`), one image / two commands, env `JOBS_BUCKET` + `HOME=/tmp`, Google SSM env only with `-c google_key=true`, S3 `jobs/*` + `weather/*`, Lambda 3008 MB / 180 s / 2 GB tmp; state machine discards P2's inline A/C and passes `jobs/{id}/job_A.json` / `report_C.json` URIs (Pass states), simulate gets `{A, B}`; timeout 10 min (API stale threshold 12 min); P1 asset keeps its Dockerfile, `extra_hash` for v2 manifests; serverless 3072 MB. New `infra/scripts/prebuild_images.py` (called by `deploy.sh`: synth -> prebuild v2 images -> deploy) and `infra/scripts/local_pipeline.py`. Stubs use `shade_C.png`; contract tests validate P2's C; `contracts/README.md` interface table updated.
- **Change in P2's area (needs P2's review):** `solar/Dockerfile` adds `RUN dnf install -y expat && dnf clean all`. Without it `import rasterio` fails in the Lambda base image (`libexpat.so.1`), so every P2 Lambda call would fail.
- **Deploy failures fixed on the way:** (1) CDK dropped P1's Dockerfile from the staged context; (2) SageMaker rejected the OCI manifest; (3) Lambda MemorySize > 3008 rejected; (4) SageMaker serverless quota 3072 MB; (5) CDK CLI `outputs` bug. Each failed stack update rolled back cleanly.
- **Also:** an earlier `--exclusively` redeploy without `SOLAR_ALERT_EMAILS` had removed the pipeline-failure alarm; restored by this deploy (emails read back from the SNS topic).
- **Tests:** see Verification results (all passed).
- **Next step:** user authorizes push (team convention: shared `p1`); teammates review the contract additions and the P2 Dockerfile line; P4 switches the web app to the live API.

### 2026-10-11 — Claude Code — P3 first deploy verified
- **Files changed:** `backend/common/s3util.py` (regional presigned URLs), `backend/tests/test_api.py` (asserts regional host), `infra/requirements-dev.txt` (+`botocore[crt]`), `TASKS.md`, `PROJECT_CONTEXT.md`.
- **Commands:** user ran `infra/scripts/deploy.sh`; `export_env.py` (after installing awscrt); `cdk deploy SolarPipeline SolarApi --exclusively` (SolarCore NOT redeployed: redeploying it without `SOLAR_ALERT_EMAILS` would remove the budget); `smoke.py` (+ `--address`). Results in Verification.
- **Tests:** `pytest backend/tests -q` → 36 passed.
- **Next step:** start Docker Desktop, test P1's container locally, `deploy.sh -c segment=real`.

### 2026-10-10 — Claude Code — P3 backend + infra scaffold (branch `p3`, off `origin/p1`)
- **Workspace:** P3 machine clones the repo to `C:/Users/HP/Desktop/VS/AWS/Rest_Azured`. The parent folder `C:/Users/HP/Desktop/VS/AWS/` holds **stale** copies of the briefs/context files from before Git — ignore them; `model.tar.gz` there was copied into `data/models/package/` (git-ignored).
- **Files created:** `contracts/schemas/A.schema.json`, `contracts/openapi.yaml`, `contracts/fixtures/report_C.json` + `shade.png` (DRAFT), `contracts/tests/test_fixtures.py`; `infra/` (`app.py`, `cdk.json`, `requirements*.txt`, `README.md`, `stacks/{config,packaging,common,core_stack,pipeline_stack,api_stack}.py`, `policies/{jobs.cedar,schema.cedarschema}`, `scripts/{deploy.sh,teardown.sh,make_installer.sh,set_google_key.sh,export_env.py,smoke.py}`, `tests/{test_policies,test_stacks}.py`); `backend/` (`api/{handler,authz,geocode,quota}.py`, `invoke_sagemaker/`, `save_result/`, `post_confirmation/`, `stubs/`, `common/s3util.py`, `tests/`); `.github/workflows/ci.yml`; `ruff.toml`; `docs/cost_log.md`. **Changed:** `.gitignore` (+`infra/.build/`), `contracts/README.md` (A/openapi/draft-C rows + pipeline step interface), `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`.
- **Decisions:** see PROJECT_CONTEXT.md "Key design decisions" (P3 rows). Notably: steps exchange S3 URIs; stub/real per step via CDK context; Cedar `Account`/`Job` entity model; GET of another user's job = 404; Quotas table (Homeowner 20/day, Installer 100/day, IST); stale running jobs (>7 min) reported failed; Lambda deps packaged with uv (no Docker); no separate SAM `template.yaml` (use `sam local invoke -t infra/cdk.out/...`).
- **Commands:** installed AWS CLI 2.37.12, SAM CLI 1.168.0, Docker Desktop (winget), CDK CLI 2.1145.0 (npm); `uv venv .venv --python 3.12` + deps; pytest/ruff/cdk synth as in Verification results. Draft report generated by a one-off script (not committed): panels packed in the fixture footprint with 0.6 m setback, 3.8 m row pitch, 0.5 m obstacle buffer; checked visually on the tile.
- **Not done:** any AWS action (no credentials on this machine), Docker build/run of P1's image (Docker Desktop not started yet), commit/push (needs user authorization).
- **Gotcha found:** Windows Python defaults to cp1252 for `read_text()` — always pass `encoding="utf-8"` (schemas contain non-ASCII).
- **Next step:** Next steps #1 (user login → bootstrap → deploy stubs → smoke test).

### 2026-10-11 ? Codex ? consolidate progress onto p1
- **Authorization/decision:** user explicitly requested pushing P2 progress onto existing `p1`; continue using that shared branch.
- **Files changed:** `PROJECT_CONTEXT.md` (branch preference), `TASKS.md` (handoff). Application code unchanged.
- **Commands/results:** fetched origin, switched to `p1`, `git merge --ff-only origin/p1` was already up to date; `git merge --ff-only p2` advanced p1 from bc5e040 to c7110b0 without conflicts. Publishing this state and workflow note with a normal push; no history rewrite or branch deletion.
- **Tests:** not rerun for branch/documentation-only work; existing P2 validation results remain recorded below.
- **Unresolved/next step:** remaining P2 external validation is unchanged; configure Google Solar credentials and run the coverage check.

### 2026-10-11 — Codex — P2 live validation and publication handoff
- **Files:** P2 implementation under `solar/`, C additions `contracts/schemas/C.schema.json` and `contracts/fixtures/{report_C.json,shade_C.png}`, plus `PROJECT_CONTEXT.md` and `TASKS.md`. No P1/P3/P4 code changes. Detailed file inventory is in the implementation entry below.
- **Live fixes:** `solar/solar/providers.py` invokes Overture's real console entry point with UTF-8 (Hindi names failed under Windows cp1252), validates complete GeoJSON, and atomically replaces downloads. `solar/tests/test_fetch.py` covers interrupted/invalid output, cache preservation and Unicode. `solar/validation/validate_buildings.py` resumes completed samples and retries invalid caches with a batch-only 120-second footprint timeout; production remains 35 seconds.
- **Live commands/results:** `solar/.venv312/Scripts/python.exe solar/run.py fetch --event solar/events/fetch_fixture.json --out data/solar/fetched_A.json` succeeded: centered 512x512 RGB, target footprint, 60 neighbors. `solar/.venv312/Scripts/python.exe solar/validation/validate_delhi.py` -> 20/20 within ±7% of PVGIS, differences +3.348% to +6.352% (mean +4.7175%), 12 distinct weather cells. Actual results are in `solar/validation/validation_delhi.csv`.
- **Building validation:** `data/solar/validation/.venv/Scripts/python.exe solar/validation/validate_buildings.py --model data/solar/validation/model --resume` -> 19 valid reports/heatmaps from 20 attempts, 8.453–37.913 seconds per simulation (excludes model startup/initial footprint lookup). Sample 09 has no P1 roof and is correctly rejected. Raw inputs/model extraction remain ignored under data/. Summary is `solar/validation/building_validation_delhi.csv`; quality limitations and visual review of samples 04/05/09/14 are documented in `solar/validation/README.md`.
- **Actual tests:** `solar/.venv312/Scripts/python.exe -m pytest solar/tests -q` -> 57 passed, 389 warnings, 84.03 seconds. After final UTF-8 fix, `solar/.venv312/Scripts/python.exe -m pytest solar/tests/test_fetch.py -q -p no:cacheprovider` -> 14 passed, 10 warnings, 3.46 seconds. No implementation changed since those runs; publication does not require another test run.
- **Container:** all 37 locked dependencies installed as Linux Python 3.12 x86_64-manylinux_2_34 binary wheels via uv cross-platform install. `solar/validation/container_smoke.py` prepares buildx/RIE verification. Docker build/runtime remains **not run**; wheel installation is not runtime verification.
- **Publication:** user explicitly authorized commit/push. Created branch `p2` from `p1` at bc5e040; current P2 source, small validation summaries and integration fixtures are prepared for publication to origin/p2. Weights, raw datasets, credentials and environments are excluded. Shared C additions still require affected-owner PR review before integration.
- **Remaining:** Docker/RIE and deployed Lambda timing; credentialed Google coverage/DSM; optional authenticated Earth Engine export; independent survey/shading measurements; financial-default validation; P3/P4 consumer review. AWS deployment remains P3-owned.
- **Next actionable step:** configure local Google Solar credentials or accessible SSM parameter and run `solar/.venv312/Scripts/python.exe solar/validation/check_coverage.py --limit 10`.

### 2026-10-10 — Codex — P2 local implementation and verification
- **Files created:** `solar/.gitignore`, `solar/Dockerfile`, `solar/Dockerfile.dockerignore`, `solar/README.md`, `solar/handlers.py`, `solar/run.py`, `solar/requirements.txt`, `solar/requirements-dev.txt`, `solar/requirements-earthengine.txt`, `solar/requirements.lock.txt`, `solar/solar/__init__.py`, `solar/solar/config.yaml`, `solar/solar/config.py`, `solar/solar/geo.py`, `solar/solar/heights.py`, `solar/solar/shading.py`, `solar/solar/layout.py`, `solar/solar/weather.py`, `solar/solar/energy.py`, `solar/solar/finance.py`, `solar/solar/storage.py`, `solar/solar/providers.py`, `solar/solar/fetch.py`, `solar/solar/report.py`, `solar/events/fetch_fixture.json`, `solar/events/simulate_fixture.json`, `solar/tests/conftest.py`, `solar/tests/test_physics.py`, `solar/tests/test_report.py`, `solar/tests/test_fetch.py`, `solar/tests/test_integration.py`, `solar/tests/test_contract_c.py`, `solar/docs/assumptions.md`, `solar/docs/coverage_delhi.md`, `solar/validation/README.md`, `solar/validation/locations.csv`, `solar/validation/validation_delhi.csv`, `solar/validation/validate_delhi.py`, `solar/validation/check_coverage.py`, `solar/validation/make_fixture.py`, `solar/validation/fixture_preview.png`, `contracts/schemas/C.schema.json`, `contracts/fixtures/report_C.json`, `contracts/fixtures/shade_C.png`.
- **Files changed:** PROJECT_CONTEXT.md, TASKS.md. Shared contract C artifacts are P2-owned additions; no A/B schema or P1/P3/P4 implementation changes. Root Docker ignore remains untouched; P2 has its own build-specific filter.
- **Decisions:** standalone Python package; config-driven constants; centered Web Mercator RGB for P1 and UTM 43N calculations with meridian convergence; deterministic neighbor/height sidecars rather than A changes; separate DSM and synthetic surfaces; representative monthly shadow geometry weighted by actual TMY beam; PVGIS irradiance offset honored; chosen layout orientation drives energy; no extra soiling deduction; no roof raises; no panels gives zero energy and nullable payback (consumer review needed). Missing neighbors/estimated heights/upstream warnings are explicit.
- **Environment commands:** initial python -m venv solar/.venv succeeded; sandbox pip install failed with WinError 10013 network restriction. Network-enabled pip installed uv in that environment; uv venv solar/.venv312 --python 3.12 installed Python 3.12.15 under ignored data/python. uv pip install --python solar/.venv312/Scripts/python.exe -r solar/requirements-dev.txt succeeded; uv --cache-dir data/uv-cache pip freeze generated the lock.
- **Verification commands/results:** solar/.venv312/Scripts/python.exe -m pytest solar/tests -q --disable-warnings -> **52 passed, 388 dependency/API deprecation warnings in 63.85 s**. Early tests caught tuple-vs-array GeoJSON serialization and artificial dawn shading on a flat DSM; both corrected. Physics tests include analytical cube shadow length/direction/no-wrap, spacing/packing, beam-only shading, subsidy tiers, zero/no-roof behavior, DSM nodata, Open Buildings raster, provider errors and S3 scoping.
- **Live weather:** solar/.venv312/Scripts/python.exe solar/run.py weather --lat 28.6039825 --lng 77.2935395 --out data/solar/weather_fixture.csv succeeded (8760 samples; PVGIS-ERA5 cache point 28.60,77.30; years 2005–2023). solar/run.py simulate --event solar/events/simulate_fixture.json --out data/solar/fixture_report.json succeeded. solar/validation/make_fixture.py regenerated C/heatmap/preview from cached real weather in **15.917 s**: 30 panels, 16.2 kW, 27273.75 kWh/year, 1683.56 kWh/kWp, 0.376% local shade loss. These are modeled outputs, not measured building accuracy. Neighbor data absent in fixture.
- **Visual QA:** viewed solar/validation/fixture_preview.png; panels align with target roof, spacing is visible, detected obstacles are excluded. Known upstream missed rooftop structures remain an assessment limitation. P4 rendering itself not verified.
- **Not run/blockers:** automatic approval review prevented the live Esri/Overture fetch command from executing because the review service hit a usage limit (not an unsafe-action finding). The subsequent 20-location PVGIS benchmark was not launched. CSV rows explicitly say not_run. Google credentials were requested but not supplied; coverage not tested. Earth Engine authentication/export not tested. Docker executable absent; Docker build, Lambda and AWS deployment not run. No P1 model loading or modification. Financial default capex/tariff/CO2 remain illustrative/unverified; central subsidy schedule checked against official sources in assumptions doc.
- **Single next actionable step:** once network execution is available, run `solar/.venv312/Scripts/python.exe solar/run.py fetch --event solar/events/fetch_fixture.json --out data/solar/fetched_A.json` to verify the fallback fetch on real providers.

### 2026-10-10 — Codex — overview and P2 readiness audit
- **Files changed:** PROJECT_CONTEXT.md (stale status corrections and integration constraints), TASKS.md (this entry). No implementation or contracts changed.
- **Checkout:** D:/rest_azured/Rest_Azured, p1 tracking origin/p1, initially clean. No solar/, backend/, infra/, web/ implementation.
- **Weights:** root model.tar.gz, 101,587,119 bytes, readable archive containing config.json, model.safetensors, metrics.json. SHA-256 c345069342ba4ba71ecd074786e8c2e7a4d22004d106b192840f18b895f3a1ea matches historical handoff prefix. No extraction or model loading performed.
- **Commands:** git status --short --branch (ownership failure); git -c safe.directory=D:/rest_azured/Rest_Azured status --short --branch (passed, process-local exception); python --version (3.10.9); Python tarfile/hashlib/importlib inspection and JSON Schema checks; python -m pytest ml/tests -q.
- **Results:** B schema and fixture validate, A/B job IDs match. Pytest could not start: No module named pytest. Shapely, pyproj, rasterio, pvlib also absent. Historical 13 passing tests are from P1 Mac, not this checkout. No Docker, AWS, inference or external API verification.
- **P2 sequence:** Python 3.12 environment; C schema/fixture per agreed contract; fixture-driven energy/finance; imagery/footprint/neighbor fetch; heights/shading/layout/heatmap; Lambda packaging; real-address validation. Google coverage check remains pending credentials; fallback work can proceed.
- **Open issues:** normalize imagery for P1; obtain neighbors independently of B; retain warnings; avoid double-counting soiling; keep layout and modeled orientation consistent; distinguish solar/civil time; define empty-roof and zero-panel behavior; verify financial defaults.
- **Single next actionable step:** create an isolated Python 3.12 environment and install P2 geospatial, solar and test dependencies.

### 2026-10-10 — Claude Code — Git setup (user-driven)
- User ran `git init`, `git remote add origin https://github.com/vedanttkhanna/Rest_Azured`, `git checkout -b p1` (remote was empty, so no `origin/main`), and staged the project files.
- **Fix:** `.gitignore` rule `data/` also ignored `ml/data/*.py`; changed to `/data/` (root only). Staged `.gitignore`, `ml/data/`, `TASKS.md`.
- Left untracked on purpose: `Screenshot 2026-10-10 at 8.58.34 AM.png` (user's file, not project content).
- **Not done by Claude:** commit and push (user runs them).
- **Next step:** user commits and pushes `p1`; open a PR into `main` once `main` exists.

### 2026-10-10 — Claude Code — P1 item 2: SageMaker package
- **Files created:** `ml/serve/serve.py`, `ml/serve/Dockerfile`, `ml/serve/requirements-serve.txt`, `ml/serve/package_model.py`, `ml/serve/invoke.py`, `ml/serve/README.md`, `ml/tests/test_serve.py`, `.dockerignore`. **Changed:** `AGENTS.md`, `TASKS.md`, `PROJECT_CONTEXT.md`.
- **Data (git-ignored):** `data/models/package/model.tar.gz` (+ `model.tar.gz.json` with sha256).
- **Decisions:** custom container (python:3.12-slim + CPU torch, stdlib HTTP server) instead of the prebuilt PyTorch image, to avoid installing extra libraries on every cold start; Serverless config 4096 MB / MaxConcurrency 2 recommended; input image via `image_s3_uri` or `image_b64`; tiles must be 512×512.
- **Commands / tests:** see Verification results.
- **Not verified:** `docker build` (no Docker/Finch here), x86_64 image, S3 download path, AWS deploy, `ap-south-1` Serverless availability.
- **Next step:** P3 builds/pushes/deploys per `ml/serve/README.md` and runs `invoke.py --endpoint`; P1 moves to the model card.

### 2026-10-10 — Claude Code — P1 item 1: contract B output
- **Files created:** `ml/serve/segment.py`, `ml/tests/test_contract_b.py`, `contracts/README.md`, `contracts/schemas/B.schema.json`, `contracts/fixtures/{job_A.json, rgb.png, seg_B.json, seg_B_preview.png}`. **Changed:** `ml/data/download_delhi_tiles.py` (+`--center`, `fetch_centered()`), `ml/requirements.txt` (+jsonschema, pytest), `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`.
- **Decisions:** footprint outline used as roof when prediction covers ≥50 % of it; touching roofs split by erosion (2.5 m) + watershed (1.0/1.5 m tested, still merged); without footprint, roof capped at 12 m radius + `warning`; obstacle classes limited to other/existing_pv/tree (what the model predicts); `warning` field documented in schema.
- **Commands / tests:** see Verification results. First no-footprint test failed (roof 737 m² vs footprint 238 m²) → cause: attached row houses share walls → added radius cap + warning, test now checks the documented fallback.
- **Unresolved:** obstacles under-detected (stair room on fixture roof missed); schemas A and C not written (P3/P2); P2's fetch step must centre tiles on the job and supply a footprint (Overture lookup works, ~10–15 s per area download).
- **Next step (P1):** item 2 — SageMaker serving container in `ml/serve/` (inference handler wrapping `segment.py`, Dockerfile, model.tar.gz, test script).

### 2026-10-10 — Claude Code — Stage B done + evaluated
- **Files changed:** `TASKS.md`, `PROJECT_CONTEXT.md` (no code changes).
- **Commands:** training finished (12 epochs, ~2.6 min/epoch); `train.py --eval-only` for both models on `delhi_fp/test` and `rid_ours/val`; `predict.py --model data/models/segformer_b2_delhi_fp/best --images data/raw/delhi_tiles_g5 --out data/predictions/delhi_g5_finetuned`; before/after sheet.
- **Results:** see Verification results.
- **Next step (P1):** write `ml/serve/postprocess.py` (mask → contract-B GeoJSON) and generate `contracts/fixtures/seg_B.json` from a real Delhi tile.

### 2026-10-10 — Claude Code — footprint auto-labels + Stage B started
- **Files created:** `ml/data/footprint_labels.py`. **Changed:** `ml/requirements.txt` (+scipy, geopandas, overturemaps), `TASKS.md`, `PROJECT_CONTEXT.md`.
- **Data (git-ignored):** `data/raw/footprints/*.parquet` (Overture buildings, 8 areas), `data/processed/delhi_fp/` (+`_preview/`, `alignment.csv`), `data/processed/delhi_fp_mix/` (symlinks).
- **Commands:** `footprint_labels.py --tiles data/raw/delhi_tiles_g5 --pred data/predictions/delhi_g5_rid_only --out data/processed/delhi_fp --test-area mayur_vihar --exclude sangam_vihar okhla`; baseline `train.py --eval-only --init data/models/segformer_b2_rid/best --data data/processed/delhi_fp --split test`; started `train.py --data data/processed/delhi_fp_mix --init data/models/segformer_b2_rid/best --lr 2e-5 --epochs 12 --out data/models/segformer_b2_delhi_fp`.
- **Decisions:** footprints as roof labels; model obstacles/PV/trees kept inside footprints; model-built pixels outside footprints = ignore; 3 px ignore band at footprint edges; area exclusions by visual review; mix 300 RID images to avoid forgetting PV/obstacles.
- **Unresolved:** footprint labels are not ground truth (missing buildings, small offsets) — Delhi roof IoU measures agreement with footprints. Buildings missing from footprints AND missed by the model are labelled background.
- **Next step (P1):** when training ends, eval `segformer_b2_delhi_fp/best` on `data/processed/delhi_fp` test and `data/processed/rid_ours` val, run `predict.py` on Delhi tiles, compare overlays.

### 2026-10-10 — Claude Code — manual labelling dropped
- **Context:** user created CVAT task (49 images, 4 labels) and imported pre-labels successfully, then decided manual correction is too much effort and asked to remove the CVAT work.
- **Deleted:** `ml/LABELING_GUIDE.md`, `ml/data/cvat_to_masks.py`, `data/labeling/batch1/` (regenerable with `make_label_batch.py`). Removed `pycocotools` from `ml/requirements.txt` (still installed in `ml/.venv`). Kept `ml/data/make_label_batch.py` (tile selection + split, reusable).
- **Not done (user's side):** the CVAT task "segmentation" (#2659002) on app.cvat.ai still exists; only the user can delete it.
- **Changed:** `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`. No tests run.
- **Next step (P1):** user picks: RID model as-is, or footprint-based auto-labels.

### 2026-10-10 — Claude Code — Delhi labelling batch set up
- **Files created:** `ml/data/make_label_batch.py`, `ml/data/cvat_to_masks.py`, `ml/LABELING_GUIDE.md`. **Changed:** `ml/requirements.txt` (+opencv-python-headless, +pycocotools), `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`.
- **Data (git-ignored):** `data/raw/delhi_tiles_g5/` (200 tiles, 8 areas × 5×5), `data/predictions/delhi_g5_rid_only/`, `data/labeling/batch1/` (images, `cvat_prelabels.zip`, `prelabels_coco.json`, `split.json`, `contact_sheet.png`).
- **Commands:** `download_delhi_tiles.py --out data/raw/delhi_tiles_g5 --grid 5 --scale 2`; `predict.py` on those; `make_label_batch.py … --per-area 7 --n-test 10 --min-built 8 --exclude rohini_0_3 rohini_4_0 rohini_1_2` (first runs with `--min-built 15` gave only 40 tiles; 3 highway tiles excluded after visual check); round-trip + RLE + Stage B smoke tests (see Verification).
- **Decisions:** labelling tool CVAT (app.cvat.ai, free, private); 4 labels `usable_roof, other_obstacle, existing_pv, tree` (matches what RID taught + what's visible at 0.26 m/px); test set = whole `mayur_vihar` area (10 tiles) to avoid spatial leakage.
- **Unresolved:** CVAT label JSON (`"type": "any"`) and COCO import of `cvat_prelabels.zip` not yet tried in the real CVAT UI. Stage B class weights clip roof/background at 0.1 vs PV 4.2; may over-predict PV — check after real fine-tune. Esri terms for uploading tiles to CVAT not reviewed.
- **Next step (P1):** create CVAT project + task per `ml/LABELING_GUIDE.md`, import pre-labels, start correcting tiles.

### 2026-10-10 — Claude Code — RID training result + first Delhi inference
- **Files changed:** `TASKS.md`, `PROJECT_CONTEXT.md` only (no code changes).
- **Commands:** checked `data/models/segformer_b2_rid/log.csv`; `ml/.venv/bin/python ml/infer/predict.py --model data/models/segformer_b2_rid/best --images data/raw/delhi_tiles --out data/predictions/delhi_rid_only` (OK, 72 overlays + summary.csv).
- **Results:** see Verification results. Training process was killed during epoch 11 (cause unknown; log ends mid progress bar; terminal tab showed a fresh prompt).
- **Decision:** use epoch-8 checkpoint; don't rerun the remaining 4 epochs (val metrics had plateaued).
- **Unresolved:** RID-only model generalises poorly to Delhi flat roofs; Delhi labels needed. RID test-split metric not computed.
- **Next step (P1):** label ~40–60 Delhi tiles (5 classes: background, usable_roof, existing_pv, tree, other_obstacle) and fine-tune from `data/models/segformer_b2_rid/best`.

### 2026-10-10 — Claude Code — local training setup + Delhi tiles
- **Files created:** `ml/requirements.txt`, `ml/train/train.py`, `ml/infer/predict.py`, `ml/data/download_delhi_tiles.py`. **Changed:** `.gitignore` (+`.venv/`), `AGENTS.md` (verified ml commands), `PROJECT_CONTEXT.md` (Esri resolution facts, training speed), `TASKS.md`.
- **Env:** `ml/.venv` (uv, Python 3.12.14, torch 2.14.1, transformers 4.57.6, MPS available).
- **Commands:** env setup (OK); smoke test `train.py --epochs 1 --limit 200 --out data/models/bench` (OK, results in Verification); first downloader version using Esri `MapServer/export` failed with HTTP 500 → rewrote to use z19 XYZ tiles; `download_delhi_tiles.py --grid 3 --scale 2` (72 tiles OK); started `train.py --epochs 15 --out data/models/segformer_b2_rid` (running).
- **Decisions:** train locally on MPS; 15 epochs (not 40) to fit ~3 h; Delhi tiles upsampled 2× to match RID scale.
- **Unresolved:** full-run metrics pending; area centre points for Dwarka/Rohini should be moved onto housing; Esri terms of use not reviewed; no Delhi labels yet so Delhi accuracy can't be measured.
- **Next step (P1):** when training ends, run `ml/.venv/bin/python ml/infer/predict.py --model data/models/segformer_b2_rid/best --images data/raw/delhi_tiles --out data/predictions/delhi_rid_only` and review overlays.

### 2026-10-10 — Claude Code — local training decision
- **Checked:** P1 machine = Apple M5, 10-core GPU, 26 GB RAM; system Python 3.9.6 with torch 2.8.0, MPS available; `uv` installed; no conda.
- **Decision:** train/fine-tune locally on MPS (not Kaggle) unless a 1-epoch benchmark is too slow.
- **No files changed** except this entry. **No tests run.**
- **Next step (P1):** write `ml/train/train.py`, benchmark one epoch on MPS.

### 2026-10-10 — Claude Code — project moved to Desktop
- **Moved:** all project files from `~/Downloads/submission/solarrooftop-team/` → `~/Desktop/SolarRooftop-AI/`; RID download `~/Downloads/m1655470` → `data/raw/RID_m1655470`; `~/Downloads/rid_ours` → `data/processed/rid_ours`. Paths in older log entries below are historical.
- **Files created:** `.gitignore` (ignores `data/`, weights, archives, `.env*`).
- **Files changed:** `PROJECT_CONTEXT.md` (location + data layout), `AGENTS.md` (data and Python 3.9 conventions), `TASKS.md`.
- **Not done:** the now-empty old folder `~/Downloads/submission/solarrooftop-team/` was not removed (blocked by a safety check). The user can delete it.
- **Rerun conversion (from repo root):** `python3 ml/data/rid_to_ours.py --rid-data data/raw/RID_m1655470/RID_dataset --out data/processed/rid_ours --fold 1 --check 6`
- **Next step (P1):** unchanged: write `ml/train/train.py`; zip `data/processed/rid_ours` for Kaggle.

### 2026-10-10 — Claude Code — P1 Step 2 done: RID converted
- **Files changed:** `ml/data/rid_to_ours.py` (GeoTIFF image input; `--fold` option replacing `--split-dir`; split read from `{train,val,test}_filenames_<fold>_rev.txt`).
- **Data (outside repo):** input `~/Downloads/m1655470/RID_dataset`; output `~/Downloads/rid_ours/{train,val,test}/{images,masks}` + `_preview/`.
- **Command:** `python3 submission/solarrooftop-team/ml/data/rid_to_ours.py --rid-data m1655470/RID_dataset --out rid_ours --fold 1 --check 6` (run from `~/Downloads`).
- **Verified:** background = 17 (segments, 77.8 % of pixels in 200 masks) and 8 (superstructures, 96.6 %), matching the RID code; output classes present: 0, 1, 6, 8, 9, 255.
- **Decision:** use RID fold 1. Folds share the same 154-image test size; folds differ in train/val.
- **Unresolved:** some roofs at tile edges or neighbouring buildings are not labelled in RID, so the model is penalised for predicting them (inherent to RID). RID licence is CC-BY-NC.
- **Next step (P1):** write `ml/train/train.py` (SegFormer-B2, Stage A on `rid_ours`) and upload `rid_ours` to Kaggle as a private dataset.

### 2026-10-10 — Claude Code — P1 Step 2: RID converter
- **Files created:** `ml/data/rid_to_ours.py`.
- **Decisions:** RID shadow -> ignore (255); dormer/window/ladder/chimney/unknown -> other_obstacle (9); pvmodule -> existing_pv (6); tree -> 8; any roof segment (16 azimuth bins + flat) -> usable_roof (1). P1 chose to skip the hand-made `seg_B.json` fixture and deliver sample output from the model instead.
- **Commands run:** `git clone --depth 1 https://github.com/TUMFTM/RID` (scratchpad, for reading the format); converter on synthetic RID-format masks.
- **Tests:** synthetic test passed (7 pixel-level mapping checks + split assignment). Not run on real RID data.
- **Unresolved:** mediatum download page blocks automated access, so it must be downloaded in a browser. Real folder names in the download not yet confirmed (script looks for `images_roof_centered_png/`, `masks_segments*/`, `masks_superstructures_*/`). If the download has no mask folders, masks must be generated from the CSV vector labels in the RID repo (not yet implemented).
- **Next step (P1):** download RID from https://doi.org/10.14459/2022mp1655470, run the converter with `--check 5`, and look at `_preview/`.

### 2026-10-10 — Claude Code — P1 feasibility concern
- **Files changed:** `PROJECT_CONTEXT.md` (Known issues: small-obstacle resolution risk), `TASKS.md` (this entry).
- **Decision:** none final. P1 must check real Delhi imagery resolution before fixing the class list.
- **Commands / tests:** none run.
- **Next step (P1):** inspect 5 Delhi localities at max zoom in Google Maps / Esri imagery, note which obstacles are visible, then choose the 10-class or merged-class plan.

### 2026-10-10 — Claude Code — shared agent context setup
- **Files created:** `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`, `CLAUDE.md`, `.agents/rules/shared-context.md`. No existing files modified.
- **Decisions:** `AGENTS.md` is the single source of shared rules; `CLAUDE.md` imports it via `@AGENTS.md`; an Antigravity always-on rule points to the same files as a fallback for versions that don't read `AGENTS.md`.
- **Commands run:** `ls -la`, `git status` (→ "not a git repository"), `find` for existing agent files (none found in repo or parent).
- **Tests:** none exist; none run.
- **Unresolved:** repo isn't under Git; Antigravity loading of `AGENTS.md` not verified on this machine.
- **Next step:** create `contracts/` (see Next steps #1).

### 2026-10-09 — Claude Code — planning
- **Files created:** `P1_ML_Segmentation.md`, `P2_Solar_Geospatial.md`, `P3_Backend_Cloud.md`, `P4_Frontend_Product.md`.
- **Commands run:** PVGIS and NASA POWER API calls for Delhi (succeeded, values in `PROJECT_CONTEXT.md`); PVWatts call (failed, non-JSON response).
- **Tests:** none.
