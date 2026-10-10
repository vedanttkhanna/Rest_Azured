"""Build and invoke the P2 image via Lambda RIE; no AWS deployment.

Requires a running local Docker daemon and fixture weather downloaded first.
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
import requests
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[2]


def docker(*args):
    return subprocess.run(["docker",*args],cwd=ROOT,check=True,text=True,capture_output=True).stdout.strip()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--image",default="solarrooftop-solar:p2")
    parser.add_argument("--skip-build",action="store_true")
    parser.add_argument("--port",type=int,default=19000)
    args=parser.parse_args()
    if not shutil.which("docker"): raise SystemExit("Docker is not installed; image has not been built or tested")
    docker("info")
    if not args.skip_build:
        build=subprocess.run(["docker","buildx","build","--platform","linux/amd64","--provenance=false","--load",
                   "-f","solar/Dockerfile","-t",args.image,"."],cwd=ROOT,check=True)
    weather=ROOT/"data/solar/weather_fixture.csv"
    if not weather.exists(): raise SystemExit("Download fixture weather with solar/run.py weather first")
    meta=json.loads(weather.with_suffix(".json").read_text())
    fixtures=ROOT/"contracts/fixtures"
    output=ROOT/"data/solar/container-smoke";output.mkdir(parents=True,exist_ok=True)
    mount=lambda p,target:f"type=bind,source={p.resolve()},target={target}"
    container=docker("run","-d","--rm","--platform","linux/amd64","-p",f"127.0.0.1:{args.port}:8080",
        "--mount",mount(fixtures,"/fixtures")+",readonly",
        "--mount",mount(weather.parent,"/weather")+",readonly",
        "--mount",mount(output,"/output"),"-e","SOLAR_OUTPUT_DIR=/output",args.image)
    try:
        endpoint=f"http://127.0.0.1:{args.port}/2015-03-31/functions/function/invocations"
        ready=False
        for _ in range(30):
            try:
                requests.get(f"http://127.0.0.1:{args.port}/",timeout=1)
                ready=True;break
            except requests.RequestException: time.sleep(1)
        if not ready: raise RuntimeError("Lambda RIE did not become ready")
        start=time.perf_counter()
        response=requests.post(endpoint,json={"A":"/fixtures/job_A.json","B":"/fixtures/seg_B.json",
                                "weather_uri":"/weather/weather_fixture.csv","weather_metadata":meta},timeout=120)
        response.raise_for_status()
        report=response.json()
        Draft202012Validator(json.loads((ROOT/"contracts/schemas/C.schema.json").read_text())).validate(report)
        result={"image":args.image,"image_id":docker("image","inspect","--format","{{.Id}}",args.image),
                "seconds":round(time.perf_counter()-start,3),"schema_valid":True,
                "panel_count":report["system"]["panel_count"],"annual_kwh":report["energy"]["annual_kwh"]}
        (output/"result.json").write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:
        docker("stop",container)


if __name__=="__main__":main()
