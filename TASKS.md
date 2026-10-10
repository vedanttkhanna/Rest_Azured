# TASKS.md — current progress & handoff log

Temporary progress only. Durable facts go to `PROJECT_CONTEXT.md`. Newest handoff entry on top.

## Current objective

Implement P2 only: local solar/geospatial engine and handoff artifacts. Complete live provider/field validation when execution access and credentials are available. P1/P3/P4 implementation is outside this task.

## Status

### Done
- [x] Research + architecture plan; 4 role briefs written (`P1_…`–`P4_….md`).
- [x] P1 Step 2: RID downloaded (`data/raw/RID_m1655470`) and converted to our classes (`data/processed/rid_ours`, fold 1: 1374 train / 352 val / 154 test). Visually checked on 2 previews.
- [x] Shared agent context system: `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`, `CLAUDE.md`, `.agents/rules/shared-context.md`.

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
- [ ] P1 next: (3) model card + metrics slide; (4) optional quality work (obstacle recall e.g. stair rooms, tree class). Hand `ml/serve/README.md` + `model.tar.gz` to P3.

### Blockers
- P2 Google Solar coverage/DSM needs locally configured credentials or an accessible SSM parameter; none supplied. Optional Earth Engine export needs project/service credentials.
- Docker/Podman/Finch and WSL distributions are absent. Container smoke runner is ready; Docker installation or an existing daemon is needed. No OS runtime installation was performed.
- Independent measured roof areas and shading observations are unavailable. Model/footprint agreement is not survey accuracy; real-building validation exposed P1 under-detection and merged roofs.

### Next steps (priority order)
1. **`contracts/`**: JSON Schemas for A, B, C + `fixtures/job_A.json`, `seg_B.json`, `report_C.json` for one real Delhi house; a schema-validation test. *(Next actionable step.)*
2. ~~git init~~ done by user 2026-10-10: remote `origin` = https://github.com/vedanttkhanna/Rest_Azured, P1 work on branch `p1`.
3. P2: Google Solar coverage check on ~10 Delhi addresses → record in `solar/docs/coverage_delhi.md`.
4. P3: AWS account, budget alarms, CDK skeleton with stub pipeline.
5. P4: `web/` scaffold with MSW mocks from fixtures.
6. P1: labelling guide + CVAT/Roboflow project; SAM 2 baseline.

### Verification results
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
