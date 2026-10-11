# PROJECT_CONTEXT.md — durable knowledge

Facts and decisions that stay true across tasks. Progress tracking goes in `TASKS.md`, not here.
Last updated: 2026-10-11.

## Purpose

SolarRooftop AI lets homeowners and solar installers in **Delhi** assess rooftop solar potential from satellite imagery: usable roof area (minus obstacles), shading from nearby buildings/obstacles, panel layout, annual kWh, and payback in ₹. Built for an AWS hackathon. Eligibility rule (from the hackathon page): use ≥1 AWS open-source tool **or** be deployed on AWS. We plan to do both.

## Current state of the repo (verified 2026-10-10)

- Contains planning docs (four role briefs `P1_ML_Segmentation.md`, `P2_Solar_Geospatial.md`, `P3_Backend_Cloud.md`, `P4_Frontend_Product.md`), these context files, and ML scripts in `ml/` (data conversion, Delhi tile download, training, inference).
- `contracts/` has schemas A (P3), B (P1), C (P2), real A/B/C fixtures, and `openapi.yaml` (P3). P1 code in `ml/`, P2 in `solar/`, P3 in `infra/` + `backend/`.
- **Git:** remote `origin` = https://github.com/vedanttkhanna/Rest_Azured. `main` is the combined integration branch for existing P1/P2/P3/P4 work. P3's commits were incorporated through shared `p1`, and P4's frontend/local pipeline through `p4` (see Branch workflow).
- Locations: P1/P2 machine `~/Desktop/SolarRooftop-AI/`; P3 machine `C:/Users/HP/Desktop/VS/AWS/Rest_Azured` (Windows 11). The P3 parent folder `C:/Users/HP/Desktop/VS/AWS/` has stale pre-Git copies of the docs — not the project.
- P3 code: `infra/` (CDK, 3 stacks) and `backend/` (Lambdas); how to run: `infra/README.md`. **Deployed 2026-10-11** to account 336881700677 / ap-south-1 with **all three real steps** (P2 fetch/simulate Lambdas, P1 SageMaker Serverless endpoint `solarrooftop-seg`); API `https://0cw3tjdvo2.execute-api.ap-south-1.amazonaws.com`.
- Local data lives in `data/` (git-ignored): `data/raw/RID_m1655470/RID_dataset/` (original TUM download, 1.4 GB) and `data/processed/rid_ours/{train,val,test}/{images,masks}` (converted, fold 1, 645 MB).

## Architecture (deployment planned; P1 local implementation exists)

```
web (Amplify) → API Gateway (Cognito JWT) → api Lambda (Cedar authz, DynamoDB, Location Service geocoding)
  → Step Functions: Fetch (P2 Lambda) → Segment (invoker Lambda → SageMaker Serverless, P1 model)
                    → Simulate (P2 Lambda) → Save (DynamoDB)
  Storage: S3 jobs/{job_id}/…, DynamoDB Jobs table, SSM for the Google API key
```
The data contracts (A RoofJob, B Segmentation GeoJSON, C Report) and HTTP routes are in the "Shared team contract" section of each `P*.md`. Detailed per-component designs live in the respective brief; don't copy them here.

## Key design decisions (and why)

| Decision | Reason |
|---|---|
| No AWS App Runner; Amplify Hosting + Lambda (ECS Express Mode as fallback) | App Runner closed to new customers on 2026-04-30 (AWS docs). |
| Serverless everywhere; SageMaker **Serverless Inference** (CPU) with a small SegFormer/U-Net | ~$200 credit budget; nothing should cost money while idle. |
| SAM 2 used only to help with labelling, not in production | Too heavy for CPU serverless; fine-tuned small model is enough. |
| RID dataset = pre-training only; build a ~200–300-tile Delhi dataset | RID is from Wartenberg, Bavaria (pitched tiled roofs, dormers). Delhi roofs are flat RCC with water tanks, stair rooms, AC units, which RID doesn't label. |
| Flat roofs: we choose panel tilt (~25°, south) and compute inter-row spacing; we don't estimate roof tilt from imagery | Most Delhi roofs are flat. |
| PVGIS for weather/irradiance, not PVWatts | PVGIS verified for Delhi; PVWatts call failed (see below). |
| Two paths for heights: Google Solar API DSM if covered, else a synthetic height raster (Open Buildings 2.5D + class-default obstacle heights) | No public LiDAR for Delhi; Google Solar has only limited India coverage. |
| Contract-first development with fixtures and stubs | Lets 4 people work in parallel without blocking. |
| Cedar policies for Homeowner vs Installer | Real authorization need + counts as an AWS open-source tool. |
| Cedar entity model: `User` in `Group`; resource `Account` (owner = caller) for create/list/batch/export, `Job` (owner) for read; GET of someone else's job → 404 | Create/batch need a resource to check ownership against; 404 avoids job-id probing. |
| Pipeline steps exchange **S3 URIs**, not documents; interface in `contracts/README.md` | Step Functions state limit is 256 KB. |
| Each step is `stub` or `real`, chosen per step by CDK context (`-c segment=real`) | Lets the pipeline run end-to-end before P1/P2 are wired in, and integrate one component at a time. SageMaker endpoint exists only when `segment=real`. |
| Budget with `IncludeCredit: false`, alerts $25/$75/$150 actual + $150 forecast | With credits included, spend nets to $0 and alerts never fire. |
| Lambda zips built at synth time with `uv pip install --python-platform x86_64-manylinux2014` (no Docker) | P3 machine is Windows; cedarpy/jsonschema need Linux wheels; keeps `cdk synth` and CI Docker-free. |
| Daily quota table (Homeowner 20, Installer 100 jobs/IST day), Delhi/NCR bbox 28.4–28.9 N, 76.8–77.4 E, batch ≤ 25 | Protects Google API + SageMaker spend; demo scope is Delhi. |
| API reports jobs still running after 7 min as `failed` | Step Functions' overall timeout skips Catch, which would leave the job stuck. |
| No separate SAM `template.yaml`; `sam local invoke -t infra/cdk.out/<Stack>.template.json` | One source of truth (CDK). |

## Verified external facts

- **PVGIS** (`re.jrc.ec.europa.eu/api/v5_3/PVcalc`, lat 28.61, lon 77.21, 1 kWp, 25° tilt, south, 14 % loss) → `radiation_db: PVGIS-ERA5`, years 2005–2023, **E_y ≈ 1612.5 kWh/yr**. Tested 2026-10-09.
- **NASA POWER** climatology, same point → `ALLSKY_SFC_SW_DWN` annual = **4.89 kWh/m²/day**. Tested 2026-10-09.
- **Google Solar API:** release notes (2026-04-15) say BASE-quality data is GA in *limited residential regions* of India. Coverage **for Delhi specifically is not yet verified**.
- **Google Open Buildings 2.5D Temporal:** covers South Asia (India), 2016–2023, ~4 m effective resolution, heights from Sentinel-2. Too coarse for rooftop obstacles.
- **RID mask format** (verified from repo code `definitions.py`, `mask_generation.py`): 512×512 PNG named `<image_id>.png`, pixel = class index. Segment masks: 0–15 = 16 azimuth bins, 16 = flat, 17 = background. Superstructure masks: 0 pvmodule, 1 dormer, 2 window, 3 ladder, 4 chimney, 5 shadow, 6 tree, 7 unknown, 8 background. Vector labels (CSV, WKT with **lat-lon order**) ship in the repo's `data/`; images come from the TUM download. Download (mediaTUM m1655470) verified: images are 512×512 RGB **GeoTIFF**s (`images_roof_centered_geotiff/`), 5 train/val/test folds (test = 154 each), data licence **CC-BY-NC** (non-commercial). Original paths in `definitions.py` are Windows-style (`\\`).
- **RID:** TUM, 1,880 buildings; superstructure classes pvmodule, dormer, window, ladder, chimney, shadow, tree, unknown; repo `github.com/TUMFTM/RID`. Literature: ~0.85 IoU roof, ~0.75 roof faces, ~0.49 superstructures.

- **Delhi imagery (Esri World Imagery):** best zoom over Delhi is **19 (~0.26 m/px)**; zoom 20 returns a "Map data not yet available" placeholder; the `MapServer/export` endpoint returned HTTP 500. RID is ~0.1 m/px, so Delhi tiles are upsampled 2× (`--scale 2`, ~0.13 m/px) to match object size. At this resolution, flat roofs, stair rooms, small water tanks and tarps are visible in dense areas (Lajpat Nagar, Sangam Vihar). Checked visually 2026-10-10.
- **Local training speed:** SegFormer-B2, batch 8, 512 px, MPS on Apple M5: ~3 s/iteration, 1.75 min for 200 train + 50 val images (one epoch).

- **RID-only model on Delhi (2026-10-10):** SegFormer-B2 trained on RID reaches 0.79 roof IoU on RID val but only partially detects Delhi flat roofs (varies by area; light concrete roofs often missed, dark PV arrays missed). Improving it needs Delhi labels from some source (manual or automatic, e.g. building footprints).

- **Manual Delhi labelling dropped (2026-10-10):** a CVAT workflow was set up and tried, but the user found correcting labels too time-consuming and chose not to label. Without human-checked Delhi labels there is no true Delhi accuracy number; training on the model's own uncorrected predictions would not improve it.

- **Overture building footprints for Delhi (checked 2026-10-10):** available for all 8 sample areas, mixed sources (OSM, Google Open Buildings, Microsoft). Quality varies by area: good in Dwarka, Vasant Kunj, Janakpuri, Lajpat Nagar, Mayur Vihar; Sangam Vihar has many buildings with no footprint; Okhla has overlapping duplicates. Model-based alignment correction does not work with the RID-only model (tested). See `ml/data/footprint_labels.py`.

- **Current best model: `data/models/segformer_b2_delhi_fp/best`** — SegFormer-B2, RID (Stage A) → fine-tuned on Delhi footprint auto-labels + 300 RID images (Stage B). Delhi roof IoU vs footprints 0.55 (RID-only 0.30); RID val roof 0.80. Known weakness: blobby masks merging across narrow lanes; tree class weak (~0.17).

- **Contract B production rules (2026-10-10):** tiles must be centred on the job point; a building footprint should always be supplied (Delhi row houses share walls, so imagery alone can't separate them — without a footprint the roof is capped at 12 m around the point with a `warning`). Implementation: `ml/serve/segment.py`; consumer notes: `contracts/README.md`.

- **Serving design (2026-10-10):** SageMaker Serverless Inference, custom container (`ml/serve/`): `GET /ping`, `POST /invocations` on :8080, model from `/opt/ml/model` (model.tar.gz with weights at root). CPU-only; ~0.8 s per request and ~1.5 GB RAM measured locally. Deploy steps: `ml/serve/README.md`.

- **P1 model package** `model.tar.gz` sha256 `c345069342ba4ba71ecd074786e8c2e7a4d22004d106b192840f18b895f3a1ea` (101,587,119 bytes) — verified on the P3 machine 2026-10-10; stored at `data/models/package/` (git-ignored).
- Model weights are intentionally excluded from Git; a fresh checkout needs a separately supplied archive/checkpoint. Local packaging/loading instructions are in [ml/serve/README.md](ml/serve/README.md), and the deployment package path is selected in [infra/stacks/config.py](infra/stacks/config.py). Placing local files does not update the deployed SageMaker model.
- Local ML setup and startup instructions are in [ml/README.md](ml/README.md). Install the development and pinned serving requirements together so local checks use the serving dependency versions. The standalone segmentation HTTP service produces B. The P4 development adapter in [web/local/server.py](web/local/server.py) connects the existing P1 model and P2 fetch/simulation directly to the GUI without a new AWS deployment; its combined environment additionally installs P2's requirements.
- The normal [web launch](web/README.md) runs a real local job API and GUI together. Each pin/coordinate job keeps its location through tile fetch, footprint selection, segmentation and solar reporting, with persistent ignored local artifacts. The local adapter is loopback-only; production retains Cognito/Cedar. Local address lookup uses the existing AWS Places adapter when credentials are configured, otherwise coordinate/pin input is required. Fixture behavior remains separate in `dev:demo` and the public Sample report.
- The [development launcher](web/scripts/dev.mjs) checks existing GUI/API health before spawning services. Repeated launches report the healthy running app's URL and exit successfully. It can use an existing healthy local API; shutdown only terminates children started by that launcher. Unrelated/demo/live port conflicts are reported without stopping their processes.
- Batch [prediction previews](ml/infer/predict.py) cover the entire satellite tile and can show several buildings. The serving/post-processing path selects the requested roof for contract B, using the supplied footprint where available; distinguish full-tile class masks from the target-building geometry in reports.
- **Verified live in ap-south-1 (2026-10-11):** HTTP API + Cognito JWT, Step Functions, DynamoDB, S3, Location Service Places v2 geocoding. Presigned S3 URLs must use the regional host (virtual addressing) or S3 returns SignatureDoesNotMatch. `aws login` credentials require `botocore[crt]` in Python.
- **New-account AWS quotas (verified 2026-10-11):** Lambda memory max 3008 MB; SageMaker serverless max 3072 MB per endpoint. SageMaker rejects OCI image manifests (Docker Desktop containerd-store default); images must be Docker v2 (`infra/scripts/prebuild_images.py`). Lambda accepts both.
- **P2 Lambda image needs `expat`** on top of `public.ecr.aws/lambda/python:3.12` (rasterio import fails otherwise).
- **Measured on AWS (2026-10-11):** warm job 16-22 s end to end; cold first job ~2 min (P2 container cold start dominates). Results identical to local runs for the same coordinates.
- **Always deploy with `SOLAR_ALERT_EMAILS` set and the same `-c fetch/segment/simulate` flags** (deploying the pipeline stack without emails removes the failure alarm).
- **Always deploy SolarCore with `SOLAR_ALERT_EMAILS` set** — without it the budget and alert subscriptions are removed.
- **Windows Python** defaults to cp1252 for `Path.read_text()`; our JSON schemas contain non-ASCII (—, ×). Always pass `encoding="utf-8"`.

## Unverified assumptions (check before relying on them)

PM Surya Ghar subsidy amounts (₹30k/kW ≤2 kW, ₹18k 3rd kW, cap ₹78k); capex ≈ ₹57,500/kW; tariff ₹7/kWh; grid CO₂ ≈ 0.71 t/MWh; default obstacle heights (tank 1.4 m, stair room 2.7 m, parapet 1.0 m…); 540 Wp panel 2.278 × 1.134 m; `ap-south-1` support for every service used (SageMaker Serverless, Location Service, Bedrock for the optional advisor; Places v2 `geo-places` Geocode; `AWS::Budgets::Budget` via CloudFormation). AWS account is new with $200 Free-Tier credits — whether it is on the **Free plan** (which reportedly restricts some services, possibly SageMaker, and closes when credits run out) is not checked yet.

## Failed approaches worth remembering

- **NREL PVWatts v8** with `DEMO_KEY` at `developer.nrel.gov/api/pvwatts/v8.json` (Delhi, `dataset=intl`) returned a non-JSON response on 2026-10-09. Cause not investigated. Use PVGIS instead.

## Known issues

- Geocoded addresses can land on a neighbouring building (seen in Mayur Vihar); the UI should let users confirm/move the pin.
- **Open risk — small obstacles may be invisible at available resolution.** Delhi imagery is satellite (~0.3–0.5 m/px), not ~0.1 m aerial like RID. A 1,000 L water tank (~1.1 m) is only ~2–4 px, so per-object detection of tanks / AC units may not be feasible. Stair rooms (~3×3 m, cast shadows) are more likely detectable. Not yet checked against real Delhi tiles. Fallback plan: merge obstacles into one `obstacle` class and apply a usable-area derating factor.

## P2 integration audit (2026-10-10)

- Contract B and C schemas and A/B/C fixtures exist. Schema A remains P3 work.
- P1 requires centered 512x512 RGB imagery and interprets bounds through Web Mercator (ml/serve/serve.py and segment.py). Normalize either imagery provider to this grid; use UTM 43N separately for simulation.
- B contains the target roof and its obstacles only. P2 must acquire neighboring building footprints/heights separately for shading. Current fixtures have no DSM or neighbors.
- Current P1 returns flat roofs and unknown obstacle heights. Preserve segmentation warnings and disclose defaults in report assumptions.
- Esri scale-2 output pixels (~0.13 m) upsample source pixels (~0.26 m), adding no physical detail.
- Existing ML tests expect extracted weights in data/models/segformer_b2_delhi_fp/best and serving archive in data/models/package/model.tar.gz. A root-level download does not satisfy these paths.

## P2 implementation (2026-10-10)

- Local entry points, deployment handoff and reproducible commands: `solar/README.md`. P2 code is independent of ML inference; it consumes A/B fixtures or P1 output. P1/P3/P4 code is untouched.
- Fetch normalizes imagery to P1 geometry and stores neighbor/height/provenance sidecars at deterministic job keys without changing A. Simulate returns C, panel GeoJSON and a Web-Mercator-aligned transparent heatmap. Shared C schema and fixture are P2 deliverables; nullable payback for zero savings should be reviewed with consumers.
- Geometry/shading are UTM 43N with true-north/grid-north correction. PVGIS irradiance timestamp offsets are honored; geometric shading affects beam only. Soiling is included in the configured total DC loss, not deducted twice.
- Synthetic and measured DSM paths are separate; estimated obstacles are never added again to a measured DSM. Open Buildings raster ingestion is supported; live Earth Engine export requires optional dependencies and credentials.
- No-roof inputs raise an error; valid roofs with no fitting panels produce zero generation and null payback. Unknown neighboring context and upstream warnings remain visible in report assumptions.
- Assumptions and source limitations: `solar/docs/assumptions.md`. External coverage/field validation status belongs in `solar/docs/coverage_delhi.md`, `solar/validation/README.md` and TASKS.md.

- Overture must be invoked through its installed console entry point (`overturemaps.cli:cli`); `python -m overturemaps` is unsupported. Force UTF-8 in the subprocess for non-ASCII building names on Windows. Footprint downloads are validated before atomic replacement to prevent interrupted downloads from becoming cached inputs.
- The repeatable P2 validation tools separate PVGIS energy-model agreement from P1-to-P2 real-building execution and independent survey accuracy. Real imagery plus model predictions are not ground truth; keep absent survey/Google reference values empty.

## P4 frontend

- `web/` is the Vite/React workspace for the local pipeline and deployed API. Setup, local/demo/AWS modes, frontend checks, and the Amplify handoff are documented in [web/README.md](web/README.md). The root [amplify.yml](amplify.yml) configures the monorepo app; hosting deployment remains P3-owned.
- AWS identity and role come from Amplify v6/Cognito ID tokens. Fixture and local workspaces have their own explicit development role selectors; the local bypass is disabled in production builds. No live fallback silently replaces an AWS result with fixtures.
- A/B/C TypeScript declarations are generated from the shared schemas. Runtime report validation uses the original draft-2020-12 C schema; tuple normalization happens only inside the type-generation tool and does not alter contracts.
- AWS report maps render C's panel GeoJSON and the job response's signed heatmap image; the deployed API does not return B outlines. The separate local adapter supplies the actual segmentation and inference tile as optional response fields for local roof/obstacle overlays, without changing A/B/C. Address input uses backend geocoding; the exact-location path is a confirmed map pin or coordinates. Advisor/autocomplete require future P3 routes.
- PDF saving uses browser print; assumptions are expanded during printing and restored afterward. Share links preserve the backend's account ownership rules. Signed heatmaps refresh before expiration and on window focus.

## Branch workflow

The user requested merging all existing features into `main` on 2026-10-11. This checkout's `main` tracks `origin/main` at `https://github.com/vedanttkhanna/Rest_Azured.git` and contains the published `p1`, `p2` and `p4` histories, including P3's backend/infrastructure commits. P4's feature branch remains `p4`, tracking `origin/p4`; `main` is the combined integration branch. Preserve feature branches and do not rewrite history or change other branches without authorization.
