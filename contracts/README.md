# contracts/

Shared data contracts between components. Definitions live in the "Shared team contract" section of every `P*.md` brief; this folder holds the machine-checkable versions. Changing a contract needs approval from every affected owner.

| File | Status |
|---|---|
| `schemas/B.schema.json` | ✅ Contract B (P1 → P2), JSON Schema 2020-12 |
| `schemas/A.schema.json` | ✅ Contract A (P3), JSON Schema 2020-12. The tile must be a 512×512 PNG/TIFF centred on the job point (P1 requirement). |
| `schemas/C.schema.json` | ⏳ not written yet (owner: P2) |
| `openapi.yaml` | ✅ HTTP API for P4 (P3): routes, request/response shapes, error codes |
| `fixtures/job_A.json` | Sample job for one real Mayur Vihar building. `image_s3_uri` points to the local `fixtures/rgb.png` instead of S3. |
| `fixtures/rgb.png` | 512×512 Esri tile **centred on the job point**, ~0.131 m/px; bounds in `job_A.json` → `image_bounds`. |
| `fixtures/seg_B.json` | **Real model output** for that job (not hand-made): 1 roof + 2 obstacles. |
| `fixtures/seg_B_preview.png` | `seg_B.json` drawn on the tile (yellow roof, red obstacles, magenta job point). |
| `fixtures/report_C.json` + `fixtures/shade.png` | **DRAFT placeholder by P3** so the stub pipeline and P4's UI have a report. Panel layout is geometrically real (fits the fixture roof, avoids its obstacles); energy/finance numbers are illustrative, not simulated. **P2 replaces both and owns contract C.** |

Regenerate `seg_B.json` / run the checks: see `ml/serve/segment.py` and `ml/tests/test_contract_b.py`.

## Notes for consumers of contract B
- Only the **target building** is returned: the roof matching `job_A.footprint`, else the one at/nearest the job point.
- **Supply a footprint whenever possible.** Delhi row houses share walls, so without a footprint the roof is capped to a 12 m radius around the point and `warning` is set — the area can then be over- or under-stated.
- `warning` also appears (with empty `features`) when no roof is found at the point.
- Obstacles currently come out as `class: "other"`, `existing_pv` or `tree` only; the model doesn't distinguish tanks/stair rooms yet. Obstacles are under-detected (e.g. some stair rooms missed). `height_m` is always `null` (P2 fills defaults).
- The tile must be **centred on the job point** (see `ml/data/download_delhi_tiles.py --center`); a building cut by the tile edge gets a truncated roof.

## Pipeline step interface (P3 ↔ P1/P2) — proposed, needs P2's approval

Step Functions passes **S3 URIs between steps, not documents** (256 KB state limit). Every step writes its output under
`s3://<jobs-bucket>/jobs/{job_id}/` and returns the URI. Raising an exception fails the job; its message is shown to the user.

| Step | Lambda event | Must write | Returns |
|---|---|---|---|
| fetch (P2 `handlers.fetch_handler`) | `{job_id, lat, lng, address, bucket}` | `rgb.png` (512×512, centred on lat/lng), `job_A.json` (contract A, valid against `schemas/A.schema.json`, with `footprint` whenever possible) | `{job_a_s3_uri}` |
| segment (P3 invoker → P1 endpoint) | `{job_id, job_a_s3_uri, bucket}` | `seg_B.json` | `{seg_b_s3_uri, roof_count, warning}` |
| simulate (P2 `handlers.simulate_handler`) | `{job_id, job_a_s3_uri, seg_b_s3_uri, bucket}` | `report_C.json`, `shade.png` (`heatmap_png_s3_uri` = its `s3://` URI) | `{report_s3_uri}` |

- If segment finds no roof (`roof_count == 0`), simulate is skipped and the job fails with a friendly message.
- P2's image runs as a Lambda container (4 GB, 120 s, x86_64); the Google API key is in SSM `/solarrooftop/google_api_key`
  (env `GOOGLE_API_KEY_PARAM` holds the name). Build context is `solar/` (the repo-root `.dockerignore` is P1's).
- Stub versions of all three steps: `backend/stubs/handler.py`.
