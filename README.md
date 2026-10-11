# ☀️ SolarRooftop AI

**Satellite-based rooftop solar potential evaluator for Delhi.**

SolarRooftop AI lets homeowners and solar installers assess a building's rooftop solar potential from a single address. It segments the roof from satellite imagery, detects obstructions such as water tanks, stair rooms, trees and existing panels, models shading from surrounding buildings, and estimates usable area, panel count, annual energy output (kWh) and financial payback in ₹.

---

## The problem

India's PM Surya Ghar scheme subsidises rooftop solar, and Delhi has millions of flat concrete rooftops. Yet homeowners don't know whether their roof is suitable, and installers spend time and money on site visits just to quote a system. Delhi rooftops are also cluttered with water tanks, stair rooms (*mumtys*), AC units and neighbouring buildings that cast shade. Generic "roof area × sunshine" calculators ignore all of this and overestimate.

## The solution

1. **Enter an address**, or drop a pin on the map.
2. **Fetch imagery**: a satellite tile centred on the building, plus its building footprint.
3. **Segment the roof**: a deep-learning model finds the roof and the obstacles on it.
4. **Simulate the sun**: hour-by-hour sun positions are ray-cast against a height map to find shaded areas.
5. **Lay out panels**: standard modules are packed onto the usable, unshaded area, with row spacing that avoids self-shading.
6. **Estimate energy and savings**: kWh per year, monthly output, system size, CO₂ avoided, subsidy, net cost and payback.
7. **Get a report** with the roof, obstacles, panel layout and a shade heatmap overlaid on the map.

**Two user types**:
- **Homeowners** get an instant report.
- **Installers** can assess many addresses in batch and export results.

---

## Architecture

```
                 ┌──────────────────────── Amazon Cognito (Homeowner / Installer groups) ───────┐
                 │                                                                             │
 Web app (AWS Amplify Hosting) ──► Amazon API Gateway ──► API Lambda (Cedar authorisation, Amazon Location geocoding)
                                                              │
                                                              ▼
                                               AWS Step Functions workflow
     ┌────────────────────┬───────────────────────────────┬─────────────────────────────┬──────────────────┐
     │ 1. Fetch           │ 2. Segment                    │ 3. Simulate                 │ 4. Save          │
     │ Lambda: tile +     │ Amazon SageMaker AI           │ Lambda: shading, panel      │ Amazon DynamoDB  │
     │ footprint → S3     │ Serverless Inference          │ layout, energy, finance     │ job status +     │
     │                    │ (roof segmentation model)     │ → report + heatmap → S3     │ report pointer   │
     └────────────────────┴───────────────────────────────┴─────────────────────────────┴──────────────────┘
                     Amazon S3 (tiles, results) · AWS SSM Parameter Store (API keys) · Amazon CloudWatch · AWS Budgets
```

### AWS services

| Service | Role |
|---|---|
| **Amazon SageMaker AI** (Serverless Inference) | Hosts the roof segmentation model in a custom CPU container. It scales to zero, so there's no cost while idle |
| **AWS Lambda** | Imagery fetch, solar simulation, API handlers |
| **AWS Step Functions** | Orchestrates fetch → segment → simulate → save, with retries and error states |
| **Amazon API Gateway** (HTTP API) | REST API with a Cognito JWT authoriser |
| **Amazon Cognito** | Sign-up and sign-in; `Homeowner` and `Installer` user groups |
| **Cedar** (AWS open source) | Fine-grained authorisation, e.g. only installers may run batch jobs |
| **Amazon S3** | Satellite tiles, segmentation output, reports, shade heatmaps |
| **Amazon DynamoDB** | Job records and status |
| **Amazon Location Service** | Address geocoding |
| **AWS Amplify Hosting** | Hosts the React web app (build config in `amplify.yml`) |
| **Amazon CloudWatch / AWS Budgets** | Logs, metrics, cost alarms |
| **Amazon ECR** | Stores the inference container image |

### Data contracts

The pipeline stages exchange three JSON documents:
- **A, Job:** location, tile, bounds, footprint.
- **B, Segmentation:** roof and obstacle polygons as WGS84 GeoJSON.
- **C, Report:** area, panels, energy, finance, heatmap.

JSON Schemas for A, B and C, real example files, and the HTTP API description (`openapi.yaml`) are in [`contracts/`](contracts/).

---

## The roof segmentation model

### Model
**SegFormer-B2** (transformer encoder with a lightweight decoder) for semantic segmentation, with 10 output classes: background, usable roof, water tank, stair room, AC unit, solar water heater, existing PV, parapet, tree and other obstacle. It is implemented with PyTorch and Hugging Face Transformers.

### Two-stage training

**Stage 1: learn what roofs look like.** The model is trained on the [**RID**](https://github.com/TUMFTM/RID) (Roof Information Dataset, TU Munich): 1,880 annotated aerial images of roofs and superstructures. RID's labels are mapped onto our classes, and shadows are ignored during training.

**Stage 2: adapt to Delhi without manual labelling.** Delhi roofs (flat concrete, dense row housing) look very different from Bavarian tiled roofs. Rather than hand-labelling, Delhi training labels are generated automatically:
- **Building footprints** from [Overture Maps](https://overturemaps.org/) (merging OpenStreetMap, Google Open Buildings and Microsoft building footprints) mark the roof.
- **Obstacles, panels and trees** predicted by the Stage-1 model are kept inside each footprint.
- Pixels the model thinks are roof but no footprint covers are **ignored**, as are thin bands along footprint edges, which absorb small misalignments.
- Localities with unreliable footprints are excluded after visual review.
- 300 RID images are mixed into fine-tuning so the model doesn't forget what it learned in Stage 1.

### Results (IoU, higher is better)

| Evaluation | Stage 1 only | After Delhi fine-tuning |
|---|---|---|
| **Roof, Delhi test locality** (Mayur Vihar, never seen in training) | 0.30 | **0.55** |
| Roof, RID validation | 0.79 | 0.80 |
| Existing solar panels, RID validation | 0.71 | 0.70 |
| Rooftop obstacles, RID validation | 0.41 | 0.42 |

Fine-tuning nearly doubles roof detection on Delhi without losing anything on RID. The Delhi score is measured against building footprints.

### From pixels to polygons

The model outputs a class mask. The post-processing step turns it into clean geometry for the target building:
1. **Separate buildings** by erosion plus a watershed split on the image.
2. **Select the target building** using the job's footprint, or else the point location.
3. **Use the footprint outline** when the prediction confirms it. Delhi row houses share walls, so footprints separate them more reliably than pixels can.
4. **Polygonise obstacles,** drop fragments under 0.3 m², and assign each obstacle to its roof.
5. **Output WGS84 GeoJSON** with a confidence score per polygon.

### Performance
| | |
|---|---|
| Inference per 512 × 512 tile (CPU) | ~0.2–0.5 s |
| End-to-end request through the server | ~0.8 s |
| Memory | ~1.5 GB, so SageMaker Serverless is configured at 3072 MB (the maximum for a new AWS account) |
| Model package | `model.tar.gz`, 101.6 MB (SafeTensors weights + config) |

---

## Solar simulation

| Step | Method |
|---|---|
| **Imagery** | Esri World Imagery, zoom 19 (~0.26 m/px), upsampled 2× to match the training scale; tiles centred on the building |
| **Heights** | Google Solar API surface model when an API key is configured; otherwise a synthetic height map from building footprints (known heights or floors, else 3.2 m × 4 floors; optional Open Buildings 2.5D raster) plus typical obstacle heights (tank ~1.4 m, stair room ~2.7 m, parapet ~1 m) |
| **Sun path** | `pvlib` solar position for every hour of a typical year |
| **Shading** | Ray-marching each roof cell toward the sun over the height map, then a shade-fraction heatmap weighted by direct irradiance |
| **Panel layout** | 540 Wp modules on the usable roof (obstacles and edge setbacks removed). On flat roofs: south-facing, ~25° tilt, with row pitch computed from the winter-solstice sun angle to avoid self-shading |
| **Energy** | `pvlib` plane-of-array irradiance from **PVGIS** typical-year weather data (Delhi ≈ 1,612 kWh per kWp per year at 25° tilt), temperature model, system and soiling losses |
| **Finance** | Capex per kW, **PM Surya Ghar** subsidy, Delhi electricity tariff, simple payback and 25-year savings, CO₂ avoided |

All constants are configurable and listed in each report's `assumptions` section.

---

## Repository structure

```
├── ml/
│   ├── data/
│   │   ├── rid_to_ours.py            # RID masks → our class scheme
│   │   ├── download_delhi_tiles.py   # Esri tiles (grids or centred on a location)
│   │   ├── footprint_labels.py       # Overture footprints + model → Delhi training labels
│   │   └── make_label_batch.py       # tile selection / pre-label export
│   ├── train/train.py                # SegFormer training & evaluation (CUDA / Apple MPS / CPU)
│   ├── infer/predict.py              # batch prediction + overlays
│   ├── serve/
│   │   ├── segment.py                # inference + polygon post-processing → contract B
│   │   ├── serve.py                  # SageMaker server: GET /ping, POST /invocations
│   │   ├── Dockerfile                # CPU inference container
│   │   ├── package_model.py          # builds model.tar.gz
│   │   ├── invoke.py                 # test client (local or SageMaker endpoint)
│   │   └── README.md                 # deployment guide
│   ├── tests/                        # schema, geometry and server tests
│   └── requirements.txt
├── solar/                           # imagery/footprints, shading, layout, energy and finance
├── backend/                         # authenticated job API and pipeline handlers
├── infra/                           # AWS CDK, deployment and smoke-check tools
├── web/                             # React homeowner and installer workspace
├── contracts/
│   ├── schemas/                     # shared A/B/C JSON Schemas
│   ├── openapi.yaml                 # HTTP API contract
│   └── fixtures/                    # job, imagery, segmentation and solar report
├── docs/                            # deployment and frontend handoff
├── amplify.yml                      # web/ build configuration for Amplify Hosting
└── data/                            # (git-ignored) model weights, downloads, local results
```

---

## Run it locally

There are three ways to run the web app on your computer. Pick one; all of them open at **http://localhost:5173**.

| Mode | What runs where | You need | Command (in `web/`) |
|---|---|---|---|
| **A. Demo** | Everything in the browser; every result is the bundled Mayur Vihar sample | Node.js | `npm run dev:demo` |
| **B. Live** | Web app on your computer; sign-in, pipeline and model run on the team's **deployed AWS backend** | Node.js | `npm run dev:live` |
| **C. Fully local** | Web app + a local job server that runs the real ML model (P1) and solar engine (P2) on your computer; no AWS account needed | Node.js, Python 3.12, `uv`, the model file, internet | `npm run dev` |

Run only one mode at a time (they share port 5173). Stop any of them with **Ctrl+C**.

### 0. Prerequisites (once)

- **Git** and **Node.js 22.12+** (Node 24 LTS recommended; check with `node --version`).
- For mode C and the tests: **Python 3.12** is installed automatically by **[uv](https://docs.astral.sh/uv/getting-started/installation/)**; install `uv` first.
- **Windows:** run every command below in **Git Bash** (comes with Git for Windows). Python environments on Windows use
  `Scripts/python.exe`; on macOS/Linux replace it with `bin/python` in the commands below.

```bash
git clone https://github.com/vedanttkhanna/Rest_Azured.git
cd Rest_Azured
cd web && npm ci && cd ..          # installs the web app's packages (~2-3 min)
```

Create the web app's settings files (not secrets: the deployed backend's public connection values, also listed in
[`docs/HANDOFF_P4.md`](docs/HANDOFF_P4.md)). `.env.production` is used by live mode, `.env.development` by demo mode
(same values, with the mock switch on). Both are git-ignored.
```bash
cat > web/.env.production <<'EOF'
VITE_API_URL=https://0cw3tjdvo2.execute-api.ap-south-1.amazonaws.com
VITE_USER_POOL_ID=ap-south-1_TDZMa24oN
VITE_USER_POOL_CLIENT_ID=3l16lr73pip6o9sbbnk258vbb7
VITE_REGION=ap-south-1
VITE_USE_MOCKS=false
EOF
sed 's/^VITE_USE_MOCKS=.*/VITE_USE_MOCKS=true/' web/.env.production > web/.env.development
```

### A. Demo mode (quickest look at the UI)

```bash
cd web && npm run dev:demo
```
Open http://localhost:5173. Use the **Demo role** selector to switch between Homeowner and Installer. No real assessment
is run: every job returns the sample report.

### B. Live mode (real results from the deployed AWS backend)

1. Make sure `web/.env.production` exists (step 0). Start the app:
   ```bash
   cd web && npm run dev:live
   ```
2. Open **http://localhost:5173**. Type exactly this address: Vite prints `http://127.0.0.1:5173`, but the backend only
   accepts requests from `localhost`; with `127.0.0.1` every request fails with "Failed to fetch".
3. **Create Account** with your e-mail, enter the 6-digit code you receive, and you're signed in as a **Homeowner**.
4. **Check a rooftop**: drag the pin onto a roof inside Delhi/NCR (or type latitude/longitude, or switch to address
   search), tick "I've checked the pin…", then **Find my solar potential**. A report normally takes 20–45 s; the first
   job after the system has been idle can take ~2 minutes (cold start).
5. **Installer features** (batch CSV, export) need an Installer account: ask the backend owner (P3) to promote your
   e-mail, then sign out and back in. Example CSV:
   ```
   address,lat,lng
   Lajpat roof,28.567755949588854,77.24373752699445
   Dwarka roof,28.58111902454872,77.05083905954604
   ```

Live mode works only while the team's AWS deployment is running. To deploy your own backend, see
[`infra/README.md`](infra/README.md).

### C. Fully local mode (real model + solar engine on your computer)

1. **Get the trained model.** The weights (`model.tar.gz`, 101.6 MB) are not stored in Git; get the file from the team.
   Put it in `data/models/package/`, check it, and unpack it where the local server expects it:
   ```bash
   mkdir -p data/models/package data/models/segformer_b2_delhi_fp/best
   # copy model.tar.gz into data/models/package/ first
   sha256sum data/models/package/model.tar.gz   # macOS: shasum -a 256 ...
   # expected: c345069342ba4ba71ecd074786e8c2e7a4d22004d106b192840f18b895f3a1ea
   tar -xzf data/models/package/model.tar.gz -C data/models/segformer_b2_delhi_fp/best
   ```
2. **Create the Python environment** (ML + solar packages, CPU-only PyTorch; ~5–10 min, ~2 GB):
   ```bash
   uv venv ml/.venv --python 3.12
   uv pip install --python ml/.venv/Scripts/python.exe \
     --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cpu \
     -r ml/requirements.txt -r ml/serve/requirements-serve.txt -r solar/requirements-dev.txt "botocore[crt]"
   ```
3. **Start everything:**
   ```bash
   cd web && npm run dev
   ```
   Wait for `Real local rooftop API ready at http://127.0.0.1:8765` (the model loads in 20–60 s), then open
   **http://localhost:5173**. Use the role selector at the top for Homeowner/Installer. Each assessment downloads a
   satellite tile and building outlines and fetches PVGIS weather, so internet access is needed. Results are kept in
   `data/local/`. Address search works only if you have AWS credentials configured; otherwise use the map pin or
   coordinates.

### Run the tests

```bash
# web app
cd web && npm test && npm run build && cd ..
# P1 model + local job server (needs the environment and model from mode C)
ml/.venv/Scripts/python.exe -m pytest ml/tests web/local/test_server.py -q
# P2 solar engine (separate environment)
uv venv solar/.venv312 --python 3.12 && uv pip install --python solar/.venv312/Scripts/python.exe -r solar/requirements.lock.txt pytest
solar/.venv312/Scripts/python.exe -m pytest solar/tests -q
# P3 backend, Cedar policies, AWS infrastructure (no AWS account needed; uses fakes)
uv venv .venv --python 3.12 && uv pip install --python .venv/Scripts/python.exe -r infra/requirements-dev.txt
.venv/Scripts/python.exe -m pytest backend/tests infra/tests contracts/tests -q
```
The infrastructure tests also need `uv` on your PATH and take a few minutes. Browser tests: see [`web/README.md`](web/README.md).

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Failed to fetch" in live mode | You opened `127.0.0.1:5173`; open `http://localhost:5173` |
| `Port 5173 is used by another server` | Another mode is still running; stop it with Ctrl+C |
| `Set up the ML/solar environment first` (mode C) | Step C.2 not done, or the environment is somewhere else |
| `The local model API did not start` (mode C) | Model not unpacked to `data/models/segformer_b2_delhi_fp/best/` (step C.1) |
| "No roof found at this location" | The pin is on a road/park; move it onto the centre of a rooftop |
| Address option disabled (mode C) | No AWS credentials; use the pin or coordinates |

---

## Developer tools

### ML tools only

```bash
uv venv ml/.venv --python 3.12 && uv pip install --python ml/.venv/Scripts/python.exe -r ml/requirements.txt
```

Analyse one rooftop from the command line (model unpacked as in mode C):
```bash
ml/.venv/Scripts/python.exe ml/data/download_delhi_tiles.py --out data/raw/jobs --center 28.6039825 77.2935395 --name demo
ml/.venv/Scripts/python.exe ml/serve/segment.py --model data/models/segformer_b2_delhi_fp/best \
  --image data/raw/jobs/demo.png --lat 28.6039825 --lng 77.2935395 --out demo_seg_B.json
```
Pass `--footprint <polygon.geojson>` for the building outline. Without it, the roof is capped to 12 m around the point and a warning is returned.

Run the inference server (same HTTP contract as the SageMaker container):
```bash
MODEL_DIR=data/models/segformer_b2_delhi_fp/best ml/.venv/Scripts/python.exe ml/serve/serve.py serve
ml/.venv/Scripts/python.exe ml/serve/invoke.py --url http://localhost:8080      # in a second terminal
```

### Deploy the AWS backend

The whole backend (Cognito, API, Step Functions, Lambdas, SageMaker Serverless endpoint, S3, DynamoDB, alerts,
budget) is one AWS CDK app. Requirements, deploy, health check and teardown: [`infra/README.md`](infra/README.md).
Model container details: [`ml/serve/README.md`](ml/serve/README.md).

### Train from scratch
1. Download RID from [mediaTUM](https://doi.org/10.14459/2022mp1655470) and convert it:
   ```bash
   ml/.venv/Scripts/python.exe ml/data/rid_to_ours.py --rid-data <RID_dataset> --out data/processed/rid_ours
   ```
2. Stage 1:
   ```bash
   ml/.venv/Scripts/python.exe ml/train/train.py --epochs 15 --out data/models/segformer_b2_rid
   ```
3. Download Delhi tiles with `download_delhi_tiles.py` and predict on them with `predict.py`.
4. Build the footprint labels with `footprint_labels.py`.
5. Stage 2: run `train.py --init data/models/segformer_b2_rid/best --lr 2e-5`.

Each script documents its full options in its docstring.

---

## API

`POST /invocations` (SageMaker endpoint)
```json
{
  "job_id": "uuid",
  "lat": 28.6039825, "lng": 77.2935395,
  "image_bounds": [77.2931962, 28.603681, 77.2938828, 28.6042839],
  "image_s3_uri": "s3://<bucket>/jobs/<job_id>/rgb.tif",
  "footprint": { "type": "Polygon", "coordinates": [[...]] }
}
```
This is the model endpoint used inside the pipeline. The public HTTP API for the web app (`POST /jobs`, `GET /jobs/{id}`, `GET /jobs`, `POST /jobs/batch`, Cognito JWT) is described in [`contracts/openapi.yaml`](contracts/openapi.yaml).

The response is a GeoJSON `FeatureCollection` with the roof (`kind: "roof"`) and its obstacles (`kind: "obstacle"`, `class`, `roof_id`, `confidence`). See [`contracts/fixtures/seg_B.json`](contracts/fixtures/seg_B.json).

---

## Limitations

- Delhi accuracy is measured against building footprints, not hand-verified labels.
- Small rooftop objects are near the limit of satellite resolution (~0.26 m/px). Some obstacles are missed, and tanks and stair rooms are currently reported together as `other`.
- Results are best when a building footprint is available; attached buildings can merge without one.
- Tree detection is weak.

## Future work

- A small hand-verified Delhi test set for an exact accuracy figure.
- Separate classes for water tanks and stair rooms; higher-resolution imagery.
- More Indian cities, and per-city fine-tuning from footprints.
- Detecting existing installations to estimate city-wide solar adoption.

---

## Data & licences

| Source | Use | Terms |
|---|---|---|
| [RID — Roof Information Dataset](https://github.com/TUMFTM/RID), TU Munich | Stage-1 training | CC-BY-NC (non-commercial) |
| [Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) | Satellite tiles | Esri terms of use |
| [Overture Maps](https://overturemaps.org/) buildings | Delhi labels, building outlines | Per-source licences (ODbL for OpenStreetMap data) |
| [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/), EU JRC | Solar irradiance | Free public service |
| [SegFormer (MiT-B2)](https://huggingface.co/nvidia/mit-b2), NVIDIA | Pre-trained backbone | See model card |

Because the model is trained partly on RID, it is for **non-commercial use**.

## Acknowledgements

TU Munich (RID), the Overture Maps Foundation and OpenStreetMap contributors, Google Open Buildings, Microsoft Building Footprints, EU JRC PVGIS, NVIDIA SegFormer, and the `pvlib` project.
