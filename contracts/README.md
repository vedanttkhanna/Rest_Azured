# contracts/

Shared data contracts between components. Definitions live in the "Shared team contract" section of every `P*.md` brief; this folder holds the machine-checkable versions. Changing a contract needs approval from every affected owner.

| File | Status |
|---|---|
| `schemas/B.schema.json` | ✅ Contract B (P1 → P2), JSON Schema 2020-12 |
| `schemas/A.schema.json` | ✅ Contract A (P3), JSON Schema 2020-12. The tile must be a 512×512 PNG/TIFF centred on the job point (P1 requirement). |
| `schemas/C.schema.json`, `fixtures/report_C.json`, `fixtures/shade_C.png` | ✅ Contract C (P2): schema + real simulated report and heatmap for the fixture building |
| `openapi.yaml` | ✅ HTTP API for P4 (P3): routes, request/response shapes, error codes |
| `fixtures/job_A.json` | Sample job for one real Mayur Vihar building. `image_s3_uri` points to the local `fixtures/rgb.png` instead of S3. |
| `fixtures/rgb.png` | 512×512 Esri tile **centred on the job point**, ~0.131 m/px; bounds in `job_A.json` → `image_bounds`. |
| `fixtures/seg_B.json` | **Real model output** for that job (not hand-made): 1 roof + 2 obstacles. |
| `fixtures/seg_B_preview.png` | `seg_B.json` drawn on the tile (yellow roof, red obstacles, magenta job point). |

Regenerate `seg_B.json` / run the checks: see `ml/serve/segment.py` and `ml/tests/test_contract_b.py`.

## Notes for consumers of contract B
- Only the **target building** is returned: the roof matching `job_A.footprint`, else the one at/nearest the job point.
- **Supply a footprint whenever possible.** Delhi row houses share walls, so without a footprint the roof is capped to a 12 m radius around the point and `warning` is set — the area can then be over- or under-stated.
- `warning` also appears (with empty `features`) when no roof is found at the point.
- Obstacles currently come out as `class: "other"`, `existing_pv` or `tree` only; the model doesn't distinguish tanks/stair rooms yet. Obstacles are under-detected (e.g. some stair rooms missed). `height_m` is always `null` (P2 fills defaults).
- The tile must be **centred on the job point** (see `ml/data/download_delhi_tiles.py --center`); a building cut by the tile edge gets a truncated roof.

## Pipeline step interface (as integrated 2026-10-11)

Everything for a job lives under `s3://<jobs-bucket>/jobs/{job_id}/`. Raising an exception fails the job; its message is shown to the user.

| Step | Lambda event (from Step Functions) | Writes | Next step gets |
|---|---|---|---|
| fetch (P2 `handlers.fetch_handler`) | `{job_id, lat, lng, address, bucket}` (extra keys ignored) | `rgb.tif` (512×512, centred), `job_A.json`, sidecars (`neighbors.geojson`, `fetch_metadata.json`, heights) | `s3://…/jobs/{job_id}/job_A.json` (inline A return is discarded) |
| segment (P3 invoker → P1 endpoint) | `{job_id, job_a_s3_uri, bucket}` | `seg_B.json` | `{seg_b_s3_uri, roof_count, warning}` |
| simulate (P2 `handlers.simulate_handler`) | `{"A": job_a_s3_uri, "B": seg_b_s3_uri, job_id, bucket}` | `report_C.json`, `shade.png` (+ weather cache under `weather/`) | `s3://…/jobs/{job_id}/report_C.json` (inline C return is discarded) |

- If segment finds no roof (`roof_count == 0`), simulate is skipped and the job fails with a friendly message.
- P2's image (`solar/Dockerfile`, repo-root context) runs as two Lambda functions, 4 GB / 180 s, x86_64, env `JOBS_BUCKET` (S3 mode) and `HOME=/tmp`.
  `GOOGLE_SOLAR_SSM_PARAMETER=/solarrooftop/google_api_key` is set only when deployed with `-c google_key=true` (after `infra/scripts/set_google_key.sh`); otherwise fetch uses Esri.
- Stub versions of all three steps: `backend/stubs/handler.py`.
