# P2 validation status

The local implementation has physics tests, schema checks, provider mocks and complete report tests. These establish software behavior; they do not establish field accuracy.

## Real fixture

`contracts/fixtures/report_C.json` is calculated from the existing Mayur Vihar A/B fixture and real PVGIS-ERA5 TMY weather at the cache-grid point 28.60, 77.30. Weather metadata records 2005–2023 inputs and the selected TMY months. The report labels synthetic height defaults and missing neighbors.

The completed local run took approximately 15.9 seconds with cached weather: 30 x 540 Wp panels (16.2 kW), 27,273.75 kWh/year, 1,683.56 kWh/kWp, 0.376% modeled local shading loss. These are calculated fixture outputs, **not validated real-building predictions**. A later run may change if configuration or provider weather changes.

`fixture_preview.png` shows P1 polygons and P2 panel layout on the supplied image. It is a diagnostic artifact, not frontend implementation. The transparent heatmap is `contracts/fixtures/shade_C.png` with overlay bounds in C. Its URI is local in the fixture, just as A's image URI is local; a cloud handler writes an actual S3 URI.

Regenerate from cached or live PVGIS weather:

```powershell
solar/.venv312/Scripts/python.exe solar/validation/make_fixture.py
```

## Twenty-location comparison

`validate_delhi.py` fetches PVGIS TMY and PVcalc for the same cache-grid point, tilt, azimuth, installed DC power, horizon choice and declared 14% system loss. It reports unshaded kWh/kWp and the ±7% comparison result. PVGIS PVcalc and this pvlib model differ in weather aggregation and temperature/inverter models, so agreement must be measured, not assumed.

`locations.csv` contains 20 public Delhi sampling locations. The live run completed for all 20: every result is within the declared ±7% comparison band, with P2 yield 3.348–6.352% above PVGIS PVcalc (mean 4.7175%). The 20 locations share 12 distinct 0.05° weather-cache points, so these are not 20 independent weather samples. See `validation_delhi.csv`. This checks unshaded energy-model agreement, not roof, obstacle or shading accuracy.

To reproduce the comparison:

```powershell
solar/.venv312/Scripts/python.exe solar/validation/validate_delhi.py
```

The script records errors per location and keeps completed rows. Raw weather/reference responses are cached under ignored `data/solar/validation/`. It does not invent hand-measured areas, Google annual generation, or shade-loss observations. To finish the full P2 field-validation milestone, obtain actual building A/B inputs plus independently measured roof area, run assessments, and record Google comparisons only where coverage is verified. The CSV reserves those columns.

## Real-building execution with the downloaded model

`validate_buildings.py` uses the existing P1 model without changing its code. It selects a 60–450 m² footprint near each public sampling point, recenters the imagery, runs P1, and passes the resulting A/B into P2. Raw images, neighboring footprints, model outputs, heatmaps and reports remain under ignored `data/solar/building_validation/`. Results are in `building_validation_delhi.csv`. The completed run produced **19 schema-valid reports and heatmaps from 20 attempted buildings**; Defence Colony returned no roof from P1 and was rejected by P2. Simulation times were 8.453–37.913 seconds locally, excluding initial model loading and footprint lookup. These are software execution results, not field-accuracy scores.

Run in a separate validation environment containing both `solar/requirements.lock.txt` and `ml/serve/requirements-serve.txt`:

```powershell
data/solar/validation/.venv/Scripts/python.exe solar/validation/validate_buildings.py --model data/solar/validation/model --resume
```

The batch allows 120 seconds for initial footprint lookup; production retains its 35-second bound. CSV fetch timing covers imagery/job creation after initial footprint lookup, so it is not complete cold-fetch latency. Cached rows retain the timings from their original run. Hand-measured area and Google generation columns remain blank because independent references are unavailable.

Visual review of samples 04, 05, 09 and 14 found upstream geometry problems:

| Sample | Supplied footprint m² | P1 roof m² | Result |
|---|---:|---:|---|
| 04, Rohini | 66.667 | 1.474 | Tiny detection; zero panels |
| 05, Rohini Sector 13 | 98.426 | 491.981 | Roof extends well beyond selected footprint |
| 09, Defence Colony | 63.797 | 0 | No roof; P2 correctly rejects assessment |
| 14, Okhla | 343.159 | 822.064 | Merged roofs extend beyond selected footprint |

These outputs must not be presented as surveyed building predictions. Footprints themselves can also be stale or offset; P2 execution cannot establish which outline is correct. This task leaves P1 unchanged.

## Remaining external verification

- Complete cold-fetch and deployed Lambda latency; the live Esri/Overture functional smoke check passed (centered 512x512 RGB, a selected target footprint and 60 neighboring buildings).
- Google coverage and downloaded RGB/DSM at real Delhi locations.
- Authenticated Open Buildings export; exported-raster use is tested locally.
- Docker build and Lambda runtime/performance; Docker is absent on this machine.
- P4 map rendering; P2 overlay geometry is tested and previewed locally.
- Current capex/tariff/CO2 defaults and residential subsidy eligibility for each assessed property.
