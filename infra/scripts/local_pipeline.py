"""Run the whole pipeline on this machine, the way AWS runs it, without Docker or AWS.

  fetch    P2 solar.fetch.fetch_job({job_id, lat, lng, address})   (live Esri imagery + Overture footprints)
  segment  HTTP POST to P1's server (ml/serve/serve.py, same /invocations contract as the SageMaker container)
  simulate P2 solar.report.simulate(A, B)                          (live PVGIS weather)
Every document is validated against contracts/schemas (A, B, C). Outputs: data/e2e/jobs/<job_id>/.

1. Start P1's model server (separate terminal, ml env):
     MODEL_DIR=data/opt_ml_model ml/.venv/Scripts/python.exe ml/serve/serve.py serve
2. Run this with P2's env:
     solar/.venv312/Scripts/python.exe infra/scripts/local_pipeline.py --lat 28.6039825 --lng 77.2935395
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "solar"))
from solar.config import load_config  # noqa: E402
from solar.fetch import fetch_job  # noqa: E402
from solar.report import simulate  # noqa: E402
from solar.storage import Store  # noqa: E402


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((ROOT / "contracts" / "schemas" / name).read_text(encoding="utf-8")))


def check(name: str, doc: dict) -> None:
    errors = sorted(validator(name).iter_errors(doc), key=str)
    if errors:
        raise SystemExit(f"FAIL {name}: {errors[0].message} at {list(errors[0].absolute_path)}")
    print(f"  valid against {name}")


def segment(url: str, job: dict) -> dict:
    payload = {k: job.get(k) for k in ("job_id", "lat", "lng", "image_bounds", "footprint")}
    payload["image_b64"] = base64.b64encode(Path(job["image_s3_uri"]).read_bytes()).decode()  # S3 read in AWS
    req = urllib.request.Request(f"{url}/invocations", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"FAIL segment: HTTP {e.code} {e.read().decode(errors='replace')}") from e
    except urllib.error.URLError as e:
        raise SystemExit(f"FAIL segment: P1 server not reachable at {url} ({e.reason}). Start it first.") from e


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=28.6039825)
    ap.add_argument("--lng", type=float, default=77.2935395)
    ap.add_argument("--address", default=None)
    ap.add_argument("--p1-url", default="http://localhost:8080")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "e2e")
    args = ap.parse_args()

    job_id = f"local-{uuid.uuid4().hex[:8]}"
    store, config = Store(args.out), load_config()
    print(f"job {job_id} at ({args.lat}, {args.lng})")

    t = time.perf_counter()
    job = fetch_job({"job_id": job_id, "lat": args.lat, "lng": args.lng, "address": args.address}, store, config)
    print(f"[1/3] fetch    {time.perf_counter() - t:5.1f}s  image={Path(job['image_s3_uri']).name} "
          f"footprint={'yes' if job.get('footprint') else 'NO'} source={job['imagery_source']}")
    check("A.schema.json", job)

    t = time.perf_counter()
    seg = segment(args.p1_url, job)
    roofs = [f for f in seg["features"] if f["properties"]["kind"] == "roof"]
    print(f"[2/3] segment  {time.perf_counter() - t:5.1f}s  roofs={len(roofs)} "
          f"obstacles={len(seg['features']) - len(roofs)}" + (f"  warning: {seg['warning']}" if seg.get("warning") else ""))
    check("B.schema.json", seg)
    store.put_json(f"jobs/{job_id}/seg_B.json", seg)
    if not roofs:
        raise SystemExit("STOP: no roof found at this point (the AWS pipeline fails the job with a friendly message)")

    t = time.perf_counter()
    report = simulate(job, seg, store, config)
    print(f"[3/3] simulate {time.perf_counter() - t:5.1f}s  panels={report['system']['panel_count']} "
          f"kW={report['system']['kw_dc']:.2f} kWh/yr={report['energy']['annual_kwh']:.0f} "
          f"shade_loss={report['energy']['shade_loss_pct']}% payback={report['finance']['payback_years']} yr")
    check("C.schema.json", report)
    print(f"PASS  outputs in {args.out / 'jobs' / job_id}")


if __name__ == "__main__":
    main()
