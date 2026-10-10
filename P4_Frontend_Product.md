# P4 — Frontend, Product & Demo

> **SolarRooftop AI** · Target city: **Delhi** · Your job: **everything the user sees + the story we tell judges**
> You own `web/`, the demo video and the slide deck. You also help P1 label data for one day.

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

1. React web app on **AWS Amplify Hosting** with Cognito login.
2. Homeowner flow: address → progress → report (map overlay, numbers, charts, PDF).
3. Installer flow: batch addresses (CSV), jobs table, CSV export.
4. (Optional) "Ask the solar advisor" chat (Strands Agents SDK, via P3's `/advisor`).
5. Demo video (2–3 min), slide deck, README with screenshots.

## 2. Stack (decided)

- **Vite + React + TypeScript**, Tailwind (or MUI — pick one, day 1).
- Auth: `aws-amplify` v6 + `@aws-amplify/ui-react` `<Authenticator>` (Cognito; values from P3's env file).
- Map: **MapLibre GL JS** with a satellite basemap (Esri World Imagery tiles, show attribution) — or Amazon Location Service maps if P3 sets it up.
- Charts: Recharts. Data fetching: TanStack Query (polls `/jobs/{id}` every 3 s until done/failed).
- Mocking: **MSW** returning `contracts/fixtures/report_C.json` — build the entire UI before the backend exists.
- PDF: print stylesheet + `window.print()` (fastest) or `@react-pdf/renderer`.

## 3. Screens

| Screen | Contents |
|---|---|
| **Landing** | One-line pitch, Delhi map hero, "Check my roof" CTA, how it works (3 steps) |
| **Login / Sign-up** | Amplify Authenticator; role badge (Homeowner / Installer) from the `cognito:groups` claim |
| **New assessment** | Address search (autocomplete via backend/Location Service) **or** click-on-map pin; Delhi bounding box only |
| **Progress** | Stepper: queued → fetching imagery → detecting roof → simulating sun & shade → done (driven by `status`) |
| **Report** ⭐ | Satellite map with layers toggles: roof outline, obstacles (colour by class), **panel layout**, **shade heatmap** (image overlay using `heatmap_bounds`). KPI tiles: usable area m², system kW, panels, annual kWh, ₹ savings/yr, payback yrs, CO₂ t/yr. Monthly kWh bar chart. Finance breakdown (capex, PM Surya Ghar subsidy, net). "Assumptions" accordion (from `report.assumptions`) + data sources. Buttons: Download PDF, Share link. |
| **My assessments** | List from `GET /jobs` |
| **Installer dashboard** | Upload CSV of addresses → `POST /jobs/batch`; table with status/kW/kWh/payback; export CSV; hidden for Homeowners (and the API also blocks it — Cedar) |
| **Advisor (optional)** | Chat panel on the report page: "Why is my shade loss high?", "What if I add 2 more panels?" |

Design notes: mobile-first (homeowners use phones), ₹ formatted with Indian grouping (`toLocaleString('en-IN')`), Hindi/English toggle is a nice touch if time permits. Show confidence honestly ("heights estimated") — judges like transparency.

## 4. Code layout

```
web/
  src/
    api/client.ts          # typed fetch wrapper, attaches Cognito JWT
    api/types.ts           # TS types for A/B/C — generate from contracts/schemas (json-schema-to-typescript)
    mocks/handlers.ts      # MSW: POST /jobs, GET /jobs/:id (walks through statuses), GET /jobs
    pages/ Landing, NewAssessment, Progress, Report, History, Installer
    components/ MapView, KpiTile, MonthlyChart, FinanceCard, AssumptionsPanel, ShadeLegend, AdvisorChat
  .env.development         # VITE_USE_MOCKS=true
  .env.production          # values from P3
  amplify.yml              # build spec
```

Run `VITE_USE_MOCKS=true npm run dev` until P3's stub API is live (M1), then switch the flag.

## 5. Amplify Hosting
- Connect the GitHub repo in the Amplify console, app root `web/`, build `npm ci && npm run build`, output `dist/`.
- Add SPA rewrite rule: `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>` → `/index.html` (200).
- Give P3 the Amplify domain for API CORS + Cognito callback URLs.
- (P3 deploys infra; connecting Amplify to the repo is fine for you to do — tell P3 so it's in the cost log.)

## 6. Labelling day (help P1)
P1 will share a labelling guide + CVAT/Roboflow project. Label ~100 Delhi tiles. Note confusing cases in the guide — it improves the dataset card.

## 7. Demo & pitch (you own the story)

**Demo script (2–3 min):**
1. Problem: Delhi has huge rooftop potential; homeowners don't know if their roof works, installers waste site visits.
2. Log in as Homeowner → type a Dwarka address → progress stepper.
3. Report: roof detected, water tank + stair room cut out, shade heatmap, 18 panels laid out, kWh, ₹ payback with PM Surya Ghar subsidy.
4. Log in as Installer → upload 10 addresses → table → export. Show a Homeowner getting 403 on batch (Cedar).
5. Architecture slide (from P3) + accuracy slide (P1) + validation slide (P2).

**Deck outline (8–10 slides):** problem · solution · live demo · how it works (ML + ray-tracing + pvlib) · Delhi dataset & metrics · validation vs. PVGIS/Google · AWS architecture & cost · business model (installers SaaS, lead-gen) · roadmap · team.

Record a backup video of the full flow **before** judging, in case the live demo fails.

## 8. Milestones

| # | Milestone | Unblocks |
|---|---|---|
| M0 (day 1) | Repo scaffold, MSW mocks from fixtures, design sketch of Report page | — |
| M1 | All screens working on mocks | Early feedback |
| M2 | Real Cognito login + stub API (after P3 M1) | — |
| M3 | Report renders real B/C (heatmap + panels overlay aligned on map) | Demo |
| M4 | Installer dashboard + PDF | — |
| M5 | Deployed on Amplify, demo video, slides | Submission |

## 9. Pitfalls
- GeoJSON is `[lng, lat]` order — MapLibre too; Leaflet uses `[lat, lng]`. Don't mix.
- Heatmap overlay must use `heatmap_bounds` exactly, or it will look shifted.
- Never store tokens in localStorage yourself — let Amplify handle it.
- Don't hard-code the API URL; always use env vars.

## 10. Definition of done
- [ ] Public Amplify URL, sign-up/login works
- [ ] Full homeowner flow on a real Delhi address
- [ ] Installer batch + export works; homeowner blocked
- [ ] Works on a phone screen
- [ ] Demo video + deck + README screenshots committed
