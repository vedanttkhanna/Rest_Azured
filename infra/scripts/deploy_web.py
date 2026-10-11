"""Build P4's web app and publish it to Amplify Hosting (manual deployment, no Git connection).

  .venv/Scripts/python.exe infra/scripts/deploy_web.py            # build + upload + wait until live
  .venv/Scripts/python.exe infra/scripts/deploy_web.py --skip-build

Steps: write web/.env.production from the deployed stacks (export_env.py) -> `npm run build` in web/ ->
zip web/dist (index.html at the zip root) -> Amplify create_deployment (gives a temporary upload URL) ->
HTTP PUT the zip -> start_deployment -> poll the job until SUCCEED. The Amplify app and its `main` branch
are created by the SolarCore stack (deploy.sh), which also allows the site's URL in the API/S3 CORS rules.
"""
from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import boto3

import dotenv  # noqa: F401  (loads .env: AWS_PROFILE, region)
import export_env

REGION = "ap-south-1"
REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "web" / "dist"


def build() -> None:
    export_env.main()  # web/.env.production = current API URL + Cognito ids
    npm = shutil.which("npm") or sys.exit("npm not found on PATH (install Node.js)")
    subprocess.run([npm, "run", "build"], cwd=REPO / "web", check=True)


def zip_dist() -> bytes:
    if not (DIST / "index.html").exists():
        sys.exit(f"{DIST / 'index.html'} not found: build first (drop --skip-build)")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(DIST.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(DIST).as_posix())
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true", help="upload the existing web/dist")
    args = ap.parse_args()

    cf = boto3.client("cloudformation", region_name=REGION)
    outputs = export_env.outputs(cf, "SolarCore")
    if "WebAppId" not in outputs:
        sys.exit("SolarCore has no WebAppId output: run infra/scripts/deploy.sh first")
    app_id, url = outputs["WebAppId"], outputs["WebUrl"]

    if not args.skip_build:
        build()
    payload = zip_dist()
    print(f"uploading {len(payload) / 1e6:.1f} MB to Amplify app {app_id} (branch main)", flush=True)

    amp = boto3.client("amplify", region_name=REGION)
    dep = amp.create_deployment(appId=app_id, branchName="main")
    req = urllib.request.Request(dep["zipUploadUrl"], data=payload, method="PUT",
                                 headers={"Content-Type": "application/zip"})
    with urllib.request.urlopen(req, timeout=300) as r:
        if r.status != 200:
            sys.exit(f"upload failed: HTTP {r.status}")
    job_id = amp.start_deployment(appId=app_id, branchName="main", jobId=dep["jobId"])["jobSummary"]["jobId"]

    status = "PENDING"
    for _ in range(120):
        status = amp.get_job(appId=app_id, branchName="main", jobId=job_id)["job"]["summary"]["status"]
        if status in ("SUCCEED", "FAILED", "CANCELLED"):
            break
        time.sleep(5)
    print(f"deployment job {job_id}: {status}")
    if status != "SUCCEED":
        sys.exit(1)
    print(f"Website live at {url}")


if __name__ == "__main__":
    main()
