# contracts/

Shared data contracts between components. Definitions live in the "Shared team contract" section of every `P*.md` brief; this folder holds the machine-checkable versions. Changing a contract needs approval from every affected owner.

| File | Status |
|---|---|
| `schemas/B.schema.json` | ✅ Contract B (P1 → P2), JSON Schema 2020-12 |
| `schemas/A.schema.json`, `schemas/C.schema.json` | ⏳ not written yet (owners: P3 for A, P2 for C) |
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
