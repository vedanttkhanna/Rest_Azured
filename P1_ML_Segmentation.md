# P1 — ML & Roof Segmentation

> **SolarRooftop AI** · Target city: **Delhi** · Your job: **satellite tile in → roof + obstacle polygons out**
> You own `ml/` in the repo. You are the only person who changes the model; you hand P3 a container image + endpoint contract.

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

1. **Delhi rooftop dataset** (~200–300 labelled tiles) + data card.
2. **Trained model** (pre-trained on RID/INRIA → fine-tuned on Delhi) with a metrics table.
3. **Inference container** that turns contract **A** into contract **B**.
4. **SageMaker endpoint contract** + container image handed to P3.
5. Model card + 2 pitch slides (approach, metrics, failure cases).

## 2. Model strategy (decided — don't re-litigate)

| Stage | What | Why |
|---|---|---|
| Labelling helper | **SAM 2** via `segment-geospatial` (samgeo), prompted with Open Buildings footprint boxes | Fast, near-free labels; *not* deployed |
| Production model | **SegFormer-B2** (or U-Net/ResNet34 via `segmentation_models_pytorch`) — semantic segmentation, 10 classes | Small enough for **SageMaker Serverless Inference (CPU, ≤6 GB, no idle cost)** — protects the $200 credit |
| Post-processing | mask → polygons (rasterio.features.shapes + shapely simplify), obstacle → parent roof assignment | Produces contract B |

**Classes (pixel labels):** `0 background, 1 usable_roof, 2 water_tank, 3 stair_room, 4 ac_unit, 5 solar_heater, 6 existing_pv, 7 parapet, 8 tree, 9 other_obstacle`

Why not RID alone: RID is Wartenberg, Bavaria (pitched tiled roofs, dormers, chimneys). Delhi = flat RCC roofs with tanks, mumtys, AC units. RID is **pre-training only**.

## 3. Data

| Dataset | Use | Link |
|---|---|---|
| RID (TUM, 1,880 buildings, ~10 cm, 512 px) | Pre-train roof/obstacle features | github.com/TUMFTM/RID · mediatum.ub.tum.de/node?id=1655470 |
| INRIA Aerial Image Labeling | Pre-train roof vs. background | project.inria.fr/aerialimagelabeling |
| Google Open Buildings v3 (India) | Footprint boxes → SAM prompts, building outlines | sites.research.google/open-buildings |
| Microsoft Global Building Footprints | Backup footprints | github.com/microsoft/GlobalMLBuildingFootprints |
| **Your Delhi set** | Fine-tune + **test set** | you create it |

**Delhi labelling plan**
- Areas (mix of building types): Dwarka, Rohini, Vasant Kunj, Lajpat Nagar, Mayur Vihar, Janakpuri, one unplanned colony (e.g. Sangam Vihar), one commercial/industrial strip (Okhla).
- Tiles: 512×512 px at ~0.13 m/px (Google zoom 20 at Delhi latitude) or best-available. Check imagery licence terms before using tiles for training; Google Solar API `dataLayers` RGB is the cleanest source if coverage exists.
- Tool: **CVAT** or **Roboflow** with SAM-assisted polygons. P4 will help label for 1 day — write a 1-page labelling guide first (class definitions + 6 example images).
- Split **by locality**, not by random tile (prevents leakage): e.g. train = 6 areas, val = 1, **test = 1 unseen area**.
- Target: 250 tiles → ~2–3 labelling person-days with SAM assist.

## 4. Training (do it OFF AWS to save credits)

- Use **Kaggle (free P100/T4 30 h/week)**, **Colab**, or a local GPU. Do *not* use SageMaker Training unless credits are clearly spare (if so, use Spot).
- Recipe: SegFormer-B2 (`nvidia/mit-b2` via HF `transformers`) · input 512 · aug: flips, 90° rotations, brightness/contrast, slight scale jitter, **haze/blur** (Delhi smog) · loss: CE + Dice · class weights for rare classes · AdamW lr 6e-5 · ~40 epochs pre-train, ~60 epochs fine-tune.
- Track with a simple CSV or Weights & Biases.

**Metrics to report (Delhi test locality):**
| Metric | Target |
|---|---|
| IoU usable_roof | ≥ 0.80 |
| mIoU obstacles | ≥ 0.45 (RID literature gets ~0.49 on superstructures) |
| Roof-area error vs. hand-measured (10 houses) | ≤ 10 % |
| Inference time per tile (CPU, serverless) | ≤ 15 s |

Also show an **ablation**: RID-only vs. Delhi-only vs. RID→Delhi. This is your best slide.

## 5. Inference container & SageMaker contract

**Folder**
```
ml/
  data/            # scripts: download RID, tile Delhi imagery, convert CVAT export -> masks
  train/           # train.py, config.yaml
  eval/            # eval.py -> metrics.json, confusion matrix
  serve/
    Dockerfile     # FROM pytorch CPU base, installs rasterio shapely transformers
    inference.py   # model_fn / input_fn / predict_fn / output_fn (SageMaker PyTorch convention)
    postprocess.py # mask -> polygons -> contract B
  tests/test_contract_B.py   # validates output against contracts/schemas/B.schema.json
  MODEL_CARD.md
```

**Endpoint I/O (agree this with P3 on day 1)**
- Request (`application/json`): `{"job_id": "...", "image_s3_uri": "s3://...", "image_bounds": [...], "gsd_m": 0.13, "footprint": {...}|null}`
- The container **reads the GeoTIFF from S3 itself** (P3 gives the endpoint role `s3:GetObject` on the jobs bucket).
- Response: contract **B** JSON.
- Must finish in < 60 s (serverless limit). If the tile is bigger than 1024², tile internally with 64 px overlap.

**Post-processing rules**
1. Keep only roof components that intersect the job's `footprint` (or the component nearest the job lat/lng if footprint null).
2. Polygonise per class, drop polygons < 0.3 m², simplify with tolerance 0.15 m (in UTM), reproject to WGS84.
3. Each obstacle gets `roof_id` of the roof polygon it overlaps most.
4. `roof_type`: flat unless the model/heights say otherwise (for Delhi, ~95 % flat). Leave `azimuth_deg`/`tilt_deg` null for flat.
5. Leave `height_m` null — P2 fills class defaults.

**Hand-off to P3:** ECR-ready Dockerfile + `model.tar.gz` (weights) + `README` with the exact request/response, memory needed (aim 4–6 GB), and a `curl`/boto3 test script. P3 deploys it as **Serverless Inference**.

## 6. Milestones

| # | Milestone | Unblocks |
|---|---|---|
| M0 (day 1) | Agree contract B + endpoint I/O with P2/P3; commit `seg_B.json` fixture (can be hand-drawn in QGIS) | P2, P3 |
| M1 | Zero-shot baseline: SAM 2 + footprints → roof polygon only, runnable locally on fixture tile | Early demo |
| M2 | Labelling guide + Delhi dataset v1 (≥150 tiles) | Training |
| M3 | Model v1 trained, metrics.json | — |
| M4 | Container passes `test_contract_B.py` locally; handed to P3 | Real integration |
| M5 | Model v2 (more data / tuning), ablation table, model card | Pitch |

## 7. Pitfalls

- **Pixel size**: never assume — read it from the GeoTIFF transform. Web-Mercator tiles shrink by cos(latitude) (×0.878 at Delhi).
- **Image offset**: footprints and imagery can be shifted 1–3 m; don't hard-clip to footprints, use them to choose components.
- **Shadows** look like obstacles; trees overhang roofs. Label what's physically on the roof; tree canopy = `tree`.
- **Haze**: Delhi imagery is often hazy; include hazy tiles in train and test.
- Don't leave any GPU instance running. If you must use one, tell P3 so it's in the cost log.

## 8. Definition of done
- [ ] `ml/serve` image returns valid contract B for the fixture and 5 random Delhi tiles
- [ ] Metrics table + ablation on unseen Delhi locality
- [ ] Dataset card (sources, licences, classes, splits, counts) + model card
- [ ] Endpoint live via P3 and called successfully from the Step Functions pipeline
