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
| **AWS Amplify Hosting** | Hosts the React web app |
| **Amazon CloudWatch / AWS Budgets** | Logs, metrics, cost alarms |
| **Amazon ECR** | Stores the inference container image |

### Data contracts

The pipeline stages exchange three JSON documents:
- **A, Job:** location, tile, bounds, footprint.
- **B, Segmentation:** roof and obstacle polygons as WGS84 GeoJSON.
- **C, Report:** area, panels, energy, finance, heatmap.

The schema for B and real example files are in [`contracts/`](contracts/).

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
| Memory | ~1.5 GB, so SageMaker Serverless is configured at 4 GB |
| Model package | `model.tar.gz`, 101.6 MB (SafeTensors weights + config) |

---

## Solar simulation

| Step | Method |
|---|---|
| **Imagery** | Esri World Imagery, zoom 19 (~0.26 m/px), upsampled 2× to match the training scale; tiles centred on the building |
| **Heights** | Google Solar API surface model where available; otherwise a synthetic height map from Google Open Buildings 2.5D heights plus typical obstacle heights (tank ~1.4 m, stair room ~2.7 m, parapet ~1 m) |
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
└── amplify.yml                      # web/ build configuration for Amplify Hosting
```

---

## Getting started

### Web workspace

The solar-themed React frontend is in [`web/`](web/README.md). It includes Cognito sign-in, map-pin assessment, pipeline progress, panel and shade overlays, energy and finance reports, saved assessments, and an Installer batch/CSV workspace.

```bash
cd web
npm ci
npm run dev
```

Open `http://localhost:5173`. The normal launch runs each selected rooftop through the trained model and P2 solar engine locally; it needs the supplied checkpoint and combined ML/solar environment described in [`web/README.md`](web/README.md). Map pins and coordinates work across the configured Delhi/NCR area. Address lookup needs AWS credentials. `npm run dev:demo` opens the fixed sample demo; `npm run dev:live` uses Cognito and the deployed AWS API configured from [`docs/HANDOFF_P4.md`](docs/HANDOFF_P4.md). See the web guide for checks and P3’s Amplify handoff.

### ML tools

**Requirements:** Python 3.12 and [uv](https://docs.astral.sh/uv/). A GPU is optional; training ran on an Apple-silicon Mac (MPS).

```bash
uv venv ml/.venv --python 3.12 && uv pip install --python ml/.venv/bin/python -r ml/requirements.txt
```

### Get the trained model
The weights (`model.tar.gz`, 101.6 MB) are distributed separately from the repository. Place the file in `data/models/package/`, then verify and unpack it:
```bash
shasum -a 256 data/models/package/model.tar.gz   # c345069342ba4ba71ecd074786e8c2e7a4d22004d106b192840f18b895f3a1ea
```
```bash
mkdir -p data/models/delhi && tar -xzf data/models/package/model.tar.gz -C data/models/delhi
```

### Analyse a rooftop
```bash
ml/.venv/bin/python ml/data/download_delhi_tiles.py --out data/raw/jobs --center 28.6039825 77.2935395 --name demo
```
```bash
ml/.venv/bin/python ml/serve/segment.py --model data/models/delhi --image data/raw/jobs/demo.png --lat 28.6039825 --lng 77.2935395 --out demo_seg_B.json
```
Pass `--footprint <polygon.geojson>` for the building outline. Without it, the roof is capped to 12 m around the point and a warning is returned.

### Run the inference server locally
```bash
MODEL_DIR=data/models/delhi ml/.venv/bin/python ml/serve/serve.py serve
```
```bash
ml/.venv/bin/python ml/serve/invoke.py --url http://localhost:8080
```

### Tests
```bash
ml/.venv/bin/python -m pytest ml/tests -q
```

### Deploy to Amazon SageMaker
Build the container, push it to Amazon ECR, upload `model.tar.gz` to S3, and create a Serverless endpoint (4096 MB, max concurrency 2). Step-by-step commands are in [`ml/serve/README.md`](ml/serve/README.md).

### Train from scratch
1. Download RID from [mediaTUM](https://doi.org/10.14459/2022mp1655470) and convert it:
   ```bash
   ml/.venv/bin/python ml/data/rid_to_ours.py --rid-data <RID_dataset> --out data/processed/rid_ours
   ```
2. Stage 1:
   ```bash
   ml/.venv/bin/python ml/train/train.py --epochs 15 --out data/models/segformer_b2_rid
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
  "image_s3_uri": "s3://<bucket>/jobs/<job_id>/rgb.png",
  "footprint": { "type": "Polygon", "coordinates": [[...]] }
}
```
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
