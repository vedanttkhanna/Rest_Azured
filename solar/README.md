# P2 solar and geospatial engine

P2 owns imagery/height acquisition and `A + B -> C`. This package does not train or modify P1, deploy AWS infrastructure, implement the backend, or build the frontend.

## Setup

Run from the repository root with Python 3.12:

```powershell
py -3.12 -m venv solar/.venv
solar/.venv/Scripts/python.exe -m pip install -r solar/requirements.lock.txt pytest
solar/.venv/Scripts/python.exe -m pytest solar/tests -q
```

On macOS/Linux, substitute `python3.12` and `solar/.venv/bin/python`. This checkout's verified environment is `solar/.venv312/Scripts/python.exe`; the initial `.venv` contains the bootstrap tool only. Dependency ranges are in `requirements.txt`; `requirements.lock.txt` records the tested versions. All 37 pinned dependencies resolved and installed as Linux x86_64 binary wheels for Python 3.12 / manylinux_2_34. Import and runtime behavior inside Docker remain unverified.

## Local commands

```powershell
# Real public weather, cached by 0.05-degree cell:
solar/.venv312/Scripts/python.exe solar/run.py weather --lat 28.6039825 --lng 77.2935395 --out data/solar/weather_fixture.csv

# Existing real A/B fixture -> report, panels and transparent heatmap:
solar/.venv312/Scripts/python.exe solar/run.py simulate --event solar/events/simulate_fixture.json --out data/solar/fixture_report.json

# Centered Esri GeoTIFF + Overture footprint/context -> A:
solar/.venv312/Scripts/python.exe solar/run.py fetch --event solar/events/fetch_fixture.json --out data/solar/fetched_A.json

# Twenty-location unshaded yield comparison against PVGIS:
solar/.venv312/Scripts/python.exe solar/validation/validate_delhi.py

# Google coverage, when credentials have been configured:
solar/.venv312/Scripts/python.exe solar/validation/check_coverage.py
```

`SOLAR_OUTPUT_DIR` defaults to `data/solar`. Outputs go under `jobs/{job_id}/`. Model weights are not needed for simulation from fixture B. A fetched job still requires P1 segmentation before calling simulate.

To use already downloaded weather, add `weather_uri` to the simulate event, plus `weather_metadata` from its JSON sidecar. This preserves PVGIS's irradiance time offset. Supplied weather without metadata is labelled `supplied_weather`, not PVGIS. Weather must have 8760 contiguous timezone-aware hourly rows and `ghi`, `dni`, `dhi`, `temp_air`, `wind_speed` columns. Synthetic test weather is used only by tests, never as a silent production fallback.

## Handler interfaces

`handlers.fetch_handler(event, context=None)` accepts `job_id`, `lat`, `lng`, optional `address`, and `provider` (`auto`, `esri`, `google_solar`, `upload`). It returns the existing contract A fields. Optional inputs:

- `footprint`: target WGS84 Polygon.
- `neighbors`: WGS84 FeatureCollection, including the target building when possible. Height properties may be `height_m`, `height`, or `num_floors`.
- `image_s3_uri`: georeferenced RGB GeoTIFF for `upload`; local paths work in local mode.
- `dsm_s3_uri`: uploaded absolute-elevation DSM.
- `building_heights_uri`: Open Buildings height-above-terrain GeoTIFF, used only for synthetic heights.
- `earth_engine_project`: opt-in authenticated Open Buildings export. Install `requirements-earthengine.txt` and configure service credentials beforehand; no interactive login is performed.
- `config`: overrides of known keys in `solar/config.yaml`.

Google credentials come from `GOOGLE_SOLAR_SSM_PARAMETER` (decrypted with the deployment role) or `GOOGLE_SOLAR_API_KEY` for local development. Never put credentials in event JSON. `auto` uses Google when configured and falls back on coverage HTTP 404 only. Authentication, quota and server errors fail clearly. Without a key it uses Esri and records that coverage was not checked.

`handlers.simulate_handler(event, context=None)` accepts:

```json
{
  "A": { "...": "complete RoofJob" },
  "B": { "...": "complete Segmentation" }
}
```

`A` and `B` can instead be JSON file paths locally or S3 URIs in cloud mode. Optional `weather_uri`, `weather_metadata`, `neighbors` and `config` support reproducible assessment. The result is contract C. No roof, mismatched IDs, invalid geometry, or invalid weather raises an exception for P3's existing failure handling. A valid roof with no fitting panels returns zero generation and `payback_years: null`; `null` means no finite payback, not zero years.

Contract C's machine-readable schema and fixture are supplied under `contracts/`. The nullable payback case and per-panel orientation details should be reviewed by P3/P4 during the normal shared-contract PR review. A/B definitions and P1 code are unchanged.

## Artifacts and sidecars

Fetch writes `job_A.json`, `rgb.tif`, `neighbors.geojson`, `fetch_metadata.json` and available height/Google validation layers to `jobs/{job_id}/`. Sidecars avoid adding fields to contract A. Simulate uses the same job prefix to retrieve them, writes `shade.png` and `report_C.json`, and returns C directly. Google annual flux is retained for validation only; it does not drive the simulation.

P1 RGB is normalized to a centered 512x512 EPSG:3857 grid. All geometry, setbacks, distances, height grids and shading operate in EPSG:32643. True-north solar azimuths are corrected for UTM meridian convergence. Panel GeoJSON is WGS84 `[longitude, latitude]`. The heatmap is resampled to north-up Web Mercator so P4 can use `heatmap_bounds` as an image overlay without rotation error.

## Lambda handoff to P3

```bash
docker buildx build --platform linux/amd64 --provenance=false --load -f solar/Dockerfile -t solarrooftop-solar:v1 .
docker run --rm -p 9000:8080 -e JOBS_BUCKET=<jobs-bucket> solarrooftop-solar:v1
```

The Dockerfile-specific ignore file overrides the root P1-only build filter. Use the same image for two functions, setting the command to `handlers.fetch_handler` or `handlers.simulate_handler`. `JOBS_BUCKET` enables S3 mode; temporary local artifacts are cleaned after each invocation. Inputs must use that bucket. P3 must configure network egress and narrowly scoped S3 read/write, optional SSM decryption, credentials, memory and timeouts. Suggested starting memory: 4096 MB. The <60-second simulation target is a local target, not a measured Lambda guarantee. Live Esri/Overture fetching works locally; complete cold-fetch timing and Docker/AWS runtime remain unverified here.

To build the image and exercise the local Lambda Runtime Interface Emulator once Docker is running:

```powershell
solar/.venv312/Scripts/python.exe solar/validation/container_smoke.py
```

This mounts cached fixture weather, validates the returned C report, records image identity and elapsed time under ignored `data/solar/container-smoke/`, and stops its test container. It does not deploy to AWS.

See [assumptions](docs/assumptions.md), [coverage status](docs/coverage_delhi.md), and [validation status](validation/README.md). Financial results are configurable estimates; roof geometry and estimated heights require a site survey before installation.
