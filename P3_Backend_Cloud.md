# P3 — Backend, Pipeline & AWS Infrastructure

> **SolarRooftop AI** · Target city: **Delhi** · Your job: **glue everything together on AWS, securely and cheaply**
> You own `infra/` and the backend Lambdas. **You are the only person who deploys.** You own the cost log.

---

## 0. Shared team contract (identical in all 4 files — do NOT change without a PR approved by everyone)

**Repo layout**
```
contracts/            # JSON schemas + fixtures (everyone reads, changes need 4 approvals)
  fixtures/job_A.json  seg_B.json  report_C.json  + rgb.tif (one real Delhi house)
ml/        -> P1      solar/  -> P2      infra/  -> P3      web/  -> P4
```

**CRS rules:** GeoJSON is always **WGS84 (EPSG:4326)**. All metric work (areas, distances, rasters) is done in **UTM 43N (EPSG:32643)** — this covers Delhi.

**A — RoofJob** (P3 creates → P1, P2 read)
```json
{ "job_id": "uuid", "lat": 28.5921, "lng": 77.0460, "address": "Sector 6, Dwarka, Delhi",
  "image_s3_uri": "s3://.../jobs/{job_id}/rgb.tif",      // GeoTIFF, georeferenced
  "image_bounds": [77.0455, 28.5917, 77.0465, 28.5925],   // minLng,minLat,maxLng,maxLat
  "gsd_m": 0.13,                                          // metres per pixel
  "dsm_s3_uri": null,                                     // height raster if Google Solar gave one
  "footprint": { "type": "Polygon", "coordinates": [...] }, // from Open Buildings, may be null
  "imagery_source": "google_solar | esri | upload" }
```

**B — Segmentation** (P1 produces → P2 consumes)
```json
{ "job_id": "uuid", "model_version": "segformer-b2-delhi-v3",
  "type": "FeatureCollection",
  "features": [
    { "type": "Feature", "geometry": {"type": "Polygon", "coordinates": [...]},
      "properties": { "id": "r1", "kind": "roof", "roof_type": "flat|pitched",
                      "azimuth_deg": null, "tilt_deg": null, "confidence": 0.93 } },
    { "type": "Feature", "geometry": {...},
      "properties": { "id": "o1", "kind": "obstacle", "roof_id": "r1",
                      "class": "water_tank|stair_room|ac_unit|solar_heater|existing_pv|parapet|tree|other",
                      "height_m": null, "confidence": 0.81 } } ] }
```
`height_m` = null means "unknown" → P2 fills defaults.

**C — Report** (P2 produces → P3 stores → P4 renders)
```json
{ "job_id": "uuid", "status": "done",
  "building": { "roof_area_m2": 112.4, "usable_area_m2": 61.0 },
  "system":   { "panel_count": 18, "panel_wp": 540, "kw_dc": 9.72, "tilt_deg": 25, "azimuth_deg": 180 },
  "panels":   { "type": "FeatureCollection", "features": [...] },
  "energy":   { "annual_kwh": 14300, "monthly_kwh": [12 numbers], "specific_yield_kwh_per_kwp": 1471,
                "shade_loss_pct": 6.2 },
  "finance":  { "capex_inr": 560000, "subsidy_inr": 78000, "net_cost_inr": 482000,
                "annual_savings_inr": 100100, "payback_years": 4.8 },
  "co2_t_per_year": 10.2,
  "heatmap_png_s3_uri": "s3://.../jobs/{job_id}/shade.png", "heatmap_bounds": [...],
  "assumptions": { ... }, "data_sources": { "weather": "PVGIS-ERA5", "heights": "open_buildings_2.5d" },
  "model_version": "..." }
```

**HTTP API** (P3 builds → P4 calls; all routes need a Cognito JWT)
| Method | Path | Body → Response |
|---|---|---|
| POST | `/jobs` | `{address}` or `{lat,lng}` → `{job_id}` |
| GET | `/jobs/{id}` | → `{job_id, status: queued\|fetching\|segmenting\|simulating\|done\|failed, report?: C, error?}` |
| GET | `/jobs` | → list of my jobs |
| POST | `/jobs/batch` | (Installer only) `{addresses: []}` → `{job_ids: []}` |
| POST | `/advisor` | (optional) `{job_id, message}` → `{reply}` |

**Team rules:** only P3 deploys to AWS · every contract change = PR + all affected owners approve · build against `contracts/fixtures/` until the real upstream exists · 15-min daily standup (done / next / blocked) · AWS region `ap-south-1` (Mumbai).

---

## 1. Your deliverables

1. Infrastructure as code (**AWS CDK, Python**) — one `cdk deploy` brings up everything.
2. HTTP API (the table above) with Cognito JWT auth + **Cedar** authorization.
3. **Step Functions** pipeline: fetch → segment → simulate → save.
4. SageMaker **Serverless Inference** endpoint for P1's model.
5. Monitoring, budget alarms, cost log, architecture diagram.

## 2. Hackathon eligibility & service choices

Rule: *use ≥1 AWS open-source tool **or** be deployed on AWS*. We do **both**:
- Deployed on AWS: SageMaker AI, Lambda, API Gateway, Step Functions, S3, DynamoDB, Cognito, CloudWatch, Amplify Hosting.
- AWS open source: **Cedar** (authorization policies), **SAM CLI / LocalStack** (local testing), optional **Strands Agents SDK** (advisor).

**Not App Runner:** closed to new customers since 30 Apr 2026. Frontend → Amplify Hosting, backend → Lambda. (ECS Express Mode is the fallback if a long-running container is ever needed.)

## 3. Architecture

```
web (Amplify) ──JWT──> API Gateway (HTTP API, Cognito JWT authorizer)
                          │
          ┌───────────────┼──────────────────────────────┐
     api Lambda (Python): create/list/get jobs, batch, Cedar authz
          │ StartExecution
          ▼
   Step Functions (Standard)
     1. Fetch      -> P2 Lambda image (fetch_handler)      -> writes A, rgb.tif to S3
     2. Segment    -> your invoker Lambda -> SageMaker Serverless endpoint (P1) -> B to S3
     3. Simulate   -> P2 Lambda image (simulate_handler)   -> C + heatmap to S3
     4. Save       -> DynamoDB status=done, report pointer
     (each step updates status in DynamoDB; Catch -> status=failed + error)
          │
   S3 (jobs/{job_id}/...)  DynamoDB (Jobs)  CloudWatch  SSM (Google API key)
```

Budget: Lambda + Step Functions + DynamoDB on-demand + serverless SageMaker ≈ near-zero idle cost. The only danger is any **provisioned** GPU endpoint — don't create one unless the team agrees, and delete it the same day.

## 4. Resources (CDK stack checklist)

- [ ] **S3** `solarrooftop-jobs-<acct>`: private, block public access, lifecycle delete after 30 days; CORS for presigned GETs from the web origin.
- [ ] **DynamoDB** `Jobs`: PK `owner_sub`, SK `job_id`; attrs `status, address, lat, lng, created_at, report_s3_uri, error, role`; GSI `job_id-index` (for lookup by id).
- [ ] **Cognito** user pool: email sign-in, groups **`Homeowner`**, **`Installer`**; app client (no secret) for the SPA; post-confirmation trigger adds new users to `Homeowner`. Installer = manually promoted for the demo.
- [ ] **API Gateway HTTP API** + JWT authorizer (Cognito) + CORS for the Amplify domain and `localhost:5173`.
- [ ] **api Lambda** (Python 3.12): routes from the contract. Geocoding with **Amazon Location Service** (Places, supports India) when `address` given.
- [ ] **Cedar authz** (`cedarpy` inside the api Lambda; Amazon Verified Permissions is the managed alternative):
  ```cedar
  permit(principal in Group::"Homeowner", action in [Action::"CreateJob", Action::"ReadJob"], resource)
    when { resource.owner == principal };
  permit(principal in Group::"Installer", action in [Action::"CreateJob", Action::"ReadJob", Action::"BatchCreate", Action::"ExportCsv"], resource)
    when { resource.owner == principal };
  forbid(principal, action == Action::"BatchCreate", resource) unless { principal in Group::"Installer" };
  ```
  Keep policies in `infra/policies/*.cedar` and unit-test them (great for the pitch).
- [ ] **Step Functions** state machine as above; retries on Lambda throttling; 5-min overall timeout.
- [ ] **ECR repos** + **Lambda container functions** for P2 (`fetch`, `simulate`; 4 GB, 120 s timeout).
- [ ] **SageMaker**: Model (P1 image in ECR + `model.tar.gz` in S3) → EndpointConfig with `ServerlessConfig {MemorySizeInMB: 6144, MaxConcurrency: 2}` → Endpoint. Execution role: `s3:GetObject` on jobs bucket. Invoker Lambda calls `invoke_endpoint`, writes B to S3.
- [ ] **SSM Parameter Store** SecureString `/solarrooftop/google_api_key` (for P2).
- [ ] **CloudWatch**: log retention 7 days; one dashboard (jobs/min, failures, step latency).
- [ ] **AWS Budgets**: alerts at $25, $75, $150 to the whole team's emails.
- [ ] Outputs exported to `web/.env.production`: `VITE_API_URL, VITE_USER_POOL_ID, VITE_USER_POOL_CLIENT_ID, VITE_REGION`.

Region: **ap-south-1** (Mumbai). If any service/feature is missing there, fall back to us-east-1 for that piece and note it.

## 5. Code layout

```
infra/
  app.py, cdk.json
  stacks/core_stack.py      # S3, DynamoDB, Cognito, SSM, budgets
  stacks/pipeline_stack.py  # Lambdas, Step Functions, SageMaker
  stacks/api_stack.py       # HTTP API + authorizer
  policies/*.cedar  + tests/test_policies.py
backend/
  api/handler.py            # routes, Cedar check, DynamoDB, StartExecution
  invoke_sagemaker/handler.py
  save_result/handler.py
  stubs/                    # stub fetch/segment/simulate returning contracts/fixtures (used until P1/P2 ready)
  tests/
template.yaml               # SAM template for local `sam local invoke` / `sam local start-api` (team dev convenience)
```

## 6. Stubs first (this is what keeps the team unblocked)

Day 1–2 you deploy the **whole pipeline with stub Lambdas** that just return `contracts/fixtures/*`. Then:
- P4 can hit a real API with real auth immediately.
- P2 swaps in their image → integration point 1.
- P1's endpoint goes live → integration point 2.

Also give P4 a **mock mode**: nothing needed from you beyond the contract — P4 uses MSW against fixture C.

## 7. Milestones

| # | Milestone | Unblocks |
|---|---|---|
| M0 (day 1) | AWS account, budget alarms, repo + CI (lint + contract-schema tests), JSON Schemas for A/B/C in `contracts/schemas/` | Everyone |
| M1 | Cognito + API + DynamoDB + stub pipeline deployed; env values sent to P4 | P4 real auth |
| M2 | Cedar policies + tests; batch endpoint | Installer features |
| M3 | P2 Lambda image in pipeline (integration 1) | Real numbers |
| M4 | P1 SageMaker serverless endpoint in pipeline (integration 2) | Full demo |
| M5 | Dashboard, cost log, architecture diagram (draw.io / AWS icons), teardown script | Pitch |

## 8. Security & cost hygiene
- No secrets in git (use SSM); `.gitignore` for `.env*`, `cdk.out`.
- Least-privilege roles per Lambda; S3 objects only via presigned URLs (15 min).
- Validate `lat/lng` inside a Delhi/NCR bounding box for the demo (~28.4–28.9 N, 76.8–77.4 E) — clear error otherwise.
- Rate-limit: max 20 jobs/user/day (protects Google API + SageMaker spend).
- `infra/teardown.sh` (cdk destroy + empty bucket) — run after judging.

## 9. Definition of done
- [ ] Fresh clone → `cdk deploy --all` works end-to-end
- [ ] Homeowner can't call `/jobs/batch` (403, Cedar), Installer can
- [ ] Real address → `done` report in < 2 min, failures show `failed` with an error message
- [ ] Budget alarms on, cost log updated, architecture diagram in `docs/`
