# P2 — Geospatial, Shading & Solar Energy Engine

> **SolarRooftop AI** · Target city: **Delhi** · Your job: **job (A) + roof polygons (B) → solar report (C)**
> You own `solar/` in the repo. You also own **imagery/height fetching** and the **validation table**. You hand P3 a Lambda container image.

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

1. `fetch` step: given lat/lng → GeoTIFF image + (if possible) height raster + footprint → fills contract **A**.
2. `simulate` step: A + B → contract **C** (shading, panel layout, energy, finance, heatmap).
3. Lambda container image with two handlers: `fetch_handler`, `simulate_handler`.
4. **Validation table**: your numbers vs. Google Solar API / PVGIS for ~20 Delhi addresses (the strongest slide in the pitch).
5. Assumptions doc (every constant, with source).

## 2. Day-1 coverage check (do this first — it decides your path)

Run Google Solar API `buildingInsights:findClosest` on ~10 Delhi addresses (Dwarka, Rohini, Vasant Kunj, Lajpat Nagar, Mayur Vihar, Janakpuri, Sangam Vihar, Okhla…). As of Apr 2026, BASE-quality data is GA in *limited residential regions* of India. 404s are not billed; free tier ≈ 10k buildingInsights + 1k dataLayers / month — verify current pricing.

- **Path 1 (coverage exists):** use `dataLayers` → RGB GeoTIFF (image for P1), DSM (0.1 m heights), mask, annual flux. Use Google's flux only for **validation**, compute your own numbers.
- **Path 2 (no coverage — always build this anyway):** imagery from Esri World Imagery / other permitted source + **synthetic height raster** (section 4).

Record results in `solar/docs/coverage_delhi.md`. Store the Google API key in SSM Parameter Store (ask P3), never in git.

## 3. Data sources (Delhi-verified)

| Need | Source | Status for Delhi |
|---|---|---|
| Sun position | `pvlib.solarposition` | ✅ global |
| Weather (TMY) | **PVGIS** `pvlib.iotools.get_pvgis_tmy(lat, lon)` | ✅ tested: PVGIS-ERA5 2005–2023; 1 kWp @25° south, 14 % loss → **~1,612 kWh/yr** |
| Cross-check irradiance | NASA POWER | ✅ tested: GHI ≈ 4.89 kWh/m²/day annual mean |
| PVWatts (NREL) | — | ❌ did not respond in our test — skip |
| Roof & neighbour heights | Google Solar DSM (if covered) | ⚠️ limited |
| Neighbour heights (fallback) | **Google Open Buildings 2.5D Temporal** (Earth Engine, 2016–2023, ~4 m, CC BY) | ✅ covers India, coarse |
| Footprints | Google Open Buildings v3 / Microsoft footprints | ✅ |
| LiDAR | — | ❌ none public for Delhi |

Cache everything per job in S3 (`jobs/{job_id}/...`) and cache PVGIS TMY per ~0.05° grid cell so you don't refetch.

## 4. Algorithms

### 4.1 Height raster (H) — 0.25 m grid, EPSG:32643, ~60 m × 60 m around the building
- **Path 1:** H = Google DSM resampled.
- **Path 2 (synthetic):**
  - Each building footprint in the window → height from Open Buildings 2.5D (fallback: 3.2 m × floors, assume G+3 = 12.8 m if unknown).
  - Target roof = its building height.
  - Obstacles from contract B add on top with class defaults (configurable):
    `water_tank 1.4 m · stair_room 2.7 m · parapet 1.0 m · ac_unit 0.8 m · solar_heater 1.5 m · existing_pv 1.2 m · tree: +3 m above roof · other 1.0 m`
  - Be explicit in the report that heights are estimated (`data_sources.heights`).

### 4.2 Shading (ray-marching on H)
- Time steps: 8760 h TMY is fine for one roof; for speed you may use 12 representative days (15th of each month) × hourly and weight by days/month.
- For each step with sun elevation > 3°: march from every cell toward the sun azimuth (step = cell size, max ~60 m). Cell is shaded if `H(p_k) > H(cell) + d_k · tan(elev)`. Vectorise with numpy array shifts (one shifted copy per step) — no per-pixel Python loops.
- **Shade fraction** per cell = Σ(beam POA × shaded) / Σ(beam POA). Output a heatmap PNG (transparent background, with `heatmap_bounds`) for P4.
- Apply shading to **beam only**; keep diffuse (optionally scale by a simple sky-view factor if time permits).

### 4.3 Usable area & panel layout (flat Delhi roofs)
1. Usable = roof polygon − obstacles buffered 0.5 m − 0.6 m edge setback inside parapet − cells with annual shade fraction > 20 %.
2. Panels: **540 Wp, 2.278 m × 1.134 m** (configurable), portrait, tilt 25°, azimuth 180° (south). On flat roofs we choose tilt — don't estimate it from imagery.
3. **Row spacing** so rows don't shade each other on 21 Dec, 9:00–15:00 solar time:
   `pitch = L·cos(tilt) + L·sin(tilt) · cos(Δaz) / tan(elev_min)` (L = panel length along slope). Compute elev_min with pvlib for Delhi.
4. Greedy rectangle packing aligned to the roof's dominant edge (minimum rotated rectangle) *or* due south — try both and keep whichever fits more panels.
5. Pitched roofs (rare): use face azimuth/tilt from B, panels flush-mounted, no row spacing.

### 4.4 Energy (pvlib)
- `get_total_irradiance` (Perez or Hay-Davies) for the chosen tilt/azimuth from TMY GHI/DNI/DHI.
- Beam × (1 − per-panel shade fraction) + diffuse → POA.
- Cell temp: `pvlib.temperature.sapm_cell` (open rack); module: PVWatts DC model, γ = −0.0035 /°C.
- System losses 14 % (soiling is high in Delhi — make soiling a separate visible assumption, default 5 %), inverter 96 %.
- Outputs: `annual_kwh`, `monthly_kwh[12]`, `specific_yield`, `shade_loss_pct`.

### 4.5 Finance & CO₂ (all configurable, **verify current values**)
- Capex ≈ ₹55,000–60,000 per kW (residential, Delhi) → default ₹57,500/kW.
- **PM Surya Ghar subsidy** (residential): ₹30,000/kW for the first 2 kW, ₹18,000 for the 3rd kW, cap ₹78,000.
- Tariff for savings: default ₹7/kWh (Delhi DISCOM slabs vary — BSES/TPDDL); net metering assumed.
- Payback = net cost / annual savings (simple), plus 25-year savings with 0.5 %/yr degradation.
- CO₂: grid factor ≈ 0.71 tCO₂/MWh (CEA baseline — verify latest).

## 5. Code layout

```
solar/
  solar/
    fetch.py        # geocode-free: takes lat/lng; Google Solar dataLayers OR Esri tile + footprints
    heights.py      # build H raster (path 1/2)
    shading.py      # sun path + ray-march + heatmap
    layout.py       # usable area + row spacing + packing
    energy.py       # pvlib model
    finance.py      # capex/subsidy/payback/CO2
    report.py       # assemble contract C
    config.yaml     # ALL constants live here
  handlers.py       # fetch_handler(event) -> A ; simulate_handler(event{A,B}) -> C
  Dockerfile        # public.ecr.aws/lambda/python:3.12 + pvlib rasterio shapely numpy pyproj pillow
  tests/            # contract tests using contracts/fixtures; unit tests for row spacing & shading on a toy raster
  validation/       # notebook + validation_delhi.csv
  docs/assumptions.md, coverage_delhi.md
```

Lambda sizing target: 3–4 GB memory, < 60 s per job. Local testing with **SAM CLI** (`sam local invoke`) — P3 will give you the template.

## 6. Validation (your pitch slide)

For ~20 Delhi buildings:
| address | roof area (ours / hand-measured) | kWh/kWp (ours / PVGIS) | annual kWh (ours / Google Solar if covered) | shade loss % |

Targets: specific yield within **±7 %** of PVGIS (same tilt, unshaded) · annual kWh within **±15 %** of Google Solar where available. Also a **toy-shading unit test**: a 3 m cube next to a flat plane must give the analytically expected shadow length at a known sun angle.

## 7. Milestones

| # | Milestone | Unblocks |
|---|---|---|
| M0 (day 1) | Coverage check done; `report_C.json` fixture committed (hand-filled but realistic) | P3, P4 |
| M1 | `energy.py` + `finance.py` working for an unshaded roof from fixture B | First real numbers |
| M2 | `fetch_handler` returns valid A (image + footprint, path 2) | P1 real tiles, P3 pipeline |
| M3 | Shading + heatmap + layout → full C from fixture B | P4 real report |
| M4 | Lambda image handed to P3, runs in pipeline | Integration |
| M5 | Validation table + assumptions doc | Pitch |

## 8. Pitfalls
- Work in **metres (EPSG:32643)**, only convert to WGS84 when writing GeoJSON.
- pvlib azimuth convention: 180° = south. Google Solar uses the same; double-check anything else.
- TMY timestamps are UTC from PVGIS; Delhi is UTC+5:30 — convert before "21 Dec 9:00–15:00".
- Don't double count: if PVGIS output already includes horizon shading (`use_horizon`), that's terrain only — fine to combine with your building shading.
- Every constant goes in `config.yaml` and is echoed in `report.assumptions` so the UI can show it.

## 9. Definition of done
- [ ] `simulate_handler(fixture A, fixture B)` → schema-valid C in < 60 s
- [ ] Works on both Path 1 and Path 2
- [ ] Heatmap PNG + panels GeoJSON render correctly in P4's map
- [ ] Validation table + assumptions doc committed
