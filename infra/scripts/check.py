"""Is SolarRooftop working? One command that checks every deployed part, runs one real job and shows the result.

  .venv/Scripts/python.exe infra/scripts/check.py                 # default: a real rooftop in Lajpat Nagar
  .venv/Scripts/python.exe infra/scripts/check.py --address "Sector 6, Dwarka, Delhi"
  .venv/Scripts/python.exe infra/scripts/check.py --lat 28.5811 --lng 77.0508 --no-open

Prints OK/FAIL per part, the job's progress with per-step timings, the report numbers, and saves a picture
(satellite tile + detected roof/obstacles + panel layout + shade heatmap) to data/check/<job_id>.png.
Creates a throw-away Homeowner user for the job and deletes it afterwards. Cost: a fraction of a cent.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

import dotenv  # noqa: F401  (loads .env)
import smoke

REGION = "ap-south-1"
REPO = Path(__file__).resolve().parents[2]
LAJPAT_NAGAR = (28.567755949588854, 77.24373752699445)  # a rooftop (P2 validation sample)
STACKS = ("SolarCore", "SolarPipeline", "SolarApi")
failures = 0


def line(label: str, ok: bool | None, detail: str = "") -> None:
    global failures
    mark = {True: "OK  ", False: "FAIL", None: "..  "}[ok]
    failures += ok is False
    print(f"{label:.<36} {mark} {detail}", flush=True)


def stack_outputs(cf, name):
    s = cf.describe_stacks(StackName=name)["Stacks"][0]
    return s["StackStatus"], {o["OutputKey"]: o["OutputValue"] for o in s.get("Outputs", [])}


def check_infra(session) -> dict:
    cf = session.client("cloudformation")
    info = {}
    statuses = {}
    for name in STACKS:
        try:
            statuses[name], outs = stack_outputs(cf, name)
            info.update(outs)
        except ClientError:
            statuses[name] = "MISSING"
    good = all(s.endswith("_COMPLETE") and "ROLLBACK" not in s.replace("UPDATE_ROLLBACK_COMPLETE", "")
               for s in statuses.values())
    line("2. Deployed stacks", good, ", ".join(f"{k}={v}" for k, v in statuses.items()))
    modes = info.get("StepModes", "?")
    line("   Pipeline steps", "stub" not in modes, modes + ("" if "stub" not in modes else "  (some steps are placeholders)"))

    if "segment=real" in modes:
        try:
            ep = session.client("sagemaker").describe_endpoint(EndpointName=info.get("EndpointName", "solarrooftop-seg"))
            line("3. ML model endpoint (SageMaker)", ep["EndpointStatus"] == "InService",
                 f"{ep['EndpointName']} {ep['EndpointStatus']} (serverless, no cost when idle)")
        except ClientError as e:
            line("3. ML model endpoint (SageMaker)", False, e.response["Error"]["Message"])
    else:
        line("3. ML model endpoint (SageMaker)", None, "not deployed (segment step is a placeholder)")

    try:
        sns = session.client("sns")
        topic = next(t["TopicArn"] for t in sns.list_topics()["Topics"] if t["TopicArn"].endswith(":solarrooftop-alerts"))
        subs = sns.list_subscriptions_by_topic(TopicArn=topic)["Subscriptions"]
        confirmed = sum(s["SubscriptionArn"] != "PendingConfirmation" for s in subs)
        pending = len(subs) - confirmed
        line("4. Failure alerts (e-mail)", confirmed > 0,
             f"{confirmed} confirmed" + (f", {pending} waiting for the Confirm link in their inbox" if pending else ""))
    except (StopIteration, ClientError) as e:
        line("4. Failure alerts (e-mail)", False, f"alerts topic not found ({e})")
    try:
        account = session.client("sts").get_caller_identity()["Account"]
        b = session.client("budgets", region_name="us-east-1").describe_budget(
            AccountId=account, BudgetName="solarrooftop-credits")["Budget"]
        spent = float(b.get("CalculatedSpend", {}).get("ActualSpend", {}).get("Amount", 0))
        line("   Budget", True, f"${spent:.2f} of ${float(b['BudgetLimit']['Amount']):.0f} spent this month "
                               "(excluding credits; AWS updates this ~3x/day)")
    except ClientError as e:
        line("   Budget", False, e.response["Error"]["Message"])
    check_website(info.get("WebUrl"))
    return info


def check_website(url: str | None) -> None:
    """Hosted site answers, and a client-side route is served the app (SPA rewrite) while .mjs stays JavaScript."""
    if not url:
        line("4b. Website (Amplify)", None, "not deployed")
        return
    def get(path):
        with urllib.request.urlopen(f"{url}{path}", timeout=20) as r:
            return r.headers.get("Content-Type", ""), r.read().decode(errors="replace")

    try:
        _, html = get("/jobs/health-check")  # a client-side route: must return the app, not 404
        chunks = re.findall(r"/assets/[\w.-]+\.js", html)
        if not chunks:
            line("4b. Website (Amplify)", False, f"{url}: page did not load the app")
            return
        workers = {w for c in chunks if "maps" in c for w in re.findall(r"assets/[\w.-]+\.mjs", get(c)[1])}
        bad = [w for w in workers if "javascript" not in get(f"/{w}")[0]]  # e.g. rewritten to index.html
        line("4b. Website (Amplify)", not bad, url if not bad else f"served as HTML, maps will not load: {bad}")
    except (urllib.error.URLError, TimeoutError) as e:
        line("4b. Website (Amplify)", False, f"{url}: {e}")


def run_job(session, body: dict, timeout: int):
    s = smoke.Smoke()
    try:
        token = s.user("check", ["Homeowner"])
        t0 = time.time()
        status, created = smoke.request("POST", f"{s.url}/jobs", token, body)
        if status != 201:
            line("5. Live test job", False, f"POST /jobs -> {status} {created}")
            return None, None
        job_id = created["job_id"]
        print(f"   job {job_id}: ", end="", flush=True)
        last, job, first = None, {}, True
        while time.time() - t0 < timeout:
            _, job = smoke.request("GET", f"{s.url}/jobs/{job_id}", token)
            if job.get("status") != last:
                last = job.get("status")
                print(f"{'' if first else ' -> '}{last} ({time.time() - t0:.0f}s)", end="", flush=True)
                first = False
            if last in ("done", "failed"):
                break
            time.sleep(2)
        print(flush=True)
        line("5. Live test job", last == "done",
             f"{last} in {time.time() - t0:.0f}s" + (f": {job.get('error')}" if last == "failed" else "")
             + ("  (first job after idle can take ~2 min: cold start)" if last == "done" and time.time() - t0 > 60 else ""))
        return job_id, job
    finally:
        s.cleanup()


def step_timings(session, job_id: str) -> None:
    sf = session.client("stepfunctions")
    arn = next(m["stateMachineArn"] for m in sf.list_state_machines()["stateMachines"]
               if m["name"] == "solarrooftop-pipeline")
    ex_arn = arn.replace(":stateMachine:", ":execution:") + f":{job_id}"
    entered, parts = {}, []
    for e in sf.get_execution_history(executionArn=ex_arn, maxResults=200)["events"]:
        if e["type"].endswith("StateEntered"):
            entered[e["stateEnteredEventDetails"]["name"]] = e["timestamp"]
        elif e["type"].endswith("StateExited"):
            name = e["stateExitedEventDetails"]["name"]
            if name in ("Fetch", "Segment", "Simulate", "Save"):
                parts.append(f"{name} {(e['timestamp'] - entered[name]).total_seconds():.1f}s")
    print(f"   steps: {' | '.join(parts)}")
    print(f"   console: https://{REGION}.console.aws.amazon.com/states/home?region={REGION}#/v2/executions/details/{ex_arn}")


def summary(job: dict) -> None:
    r = job["report"]
    b, sy, en, fi = r["building"], r["system"], r["energy"], r["finance"]
    payback = "never (no savings)" if fi.get("payback_years") is None else f"{fi['payback_years']:.1f} years"
    print(f"   roof {b['roof_area_m2']:.0f} m2, usable {b['usable_area_m2']:.0f} m2 -> {sy['panel_count']} panels x "
          f"{sy['panel_wp']} Wp = {sy['kw_dc']:.1f} kW")
    print(f"   {en['annual_kwh']:,.0f} kWh/year, shade loss {en['shade_loss_pct']}%, saves Rs {fi['annual_savings_inr']:,.0f}/year, "
          f"net cost Rs {fi['net_cost_inr']:,.0f} after Rs {fi['subsidy_inr']:,.0f} subsidy, payback {payback}")
    print(f"   data: weather={r['data_sources'].get('weather')}, imagery={r['data_sources'].get('imagery')}, "
          f"model={r.get('model_version')}")


def mercator(lng: float, lat: float) -> tuple[float, float]:
    return lng, math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def picture(session, job_id: str, job: dict, open_it: bool) -> None:
    from PIL import Image, ImageDraw

    s3 = session.client("s3")
    bucket = s3util_bucket(job)
    get = lambda key: s3.get_object(Bucket=bucket, Key=key)["Body"].read()  # noqa: E731
    a = json.loads(get(f"jobs/{job_id}/job_A.json"))
    seg = json.loads(get(f"jobs/{job_id}/seg_B.json"))
    report = job["report"]
    img = Image.open(io.BytesIO(get(a["image_s3_uri"].split("/", 3)[3]))).convert("RGBA")
    w, h = img.size
    x0, y0 = mercator(a["image_bounds"][0], a["image_bounds"][1])
    x1, y1 = mercator(a["image_bounds"][2], a["image_bounds"][3])

    def px(p):
        x, y = mercator(*p)
        return ((x - x0) / (x1 - x0) * w, (y1 - y) / (y1 - y0) * h)

    if report.get("heatmap_png_s3_uri", "").startswith("s3://"):
        heat = Image.open(io.BytesIO(get(report["heatmap_png_s3_uri"].split("/", 3)[3]))).convert("RGBA")
        hb = report["heatmap_bounds"]
        (hx0, hy1), (hx1, hy0) = px((hb[0], hb[3])), px((hb[2], hb[1]))
        heat = heat.resize((max(1, round(hx1 - hx0)), max(1, round(hy0 - hy1))))
        img.alpha_composite(heat, (round(hx0), round(hy1)))
    draw = ImageDraw.Draw(img)
    for f in seg["features"]:
        roof = f["properties"]["kind"] == "roof"
        draw.polygon([px(p) for p in f["geometry"]["coordinates"][0]], outline="yellow" if roof else "red", width=2)
    for f in report["panels"]["features"]:
        draw.polygon([px(p) for p in f["geometry"]["coordinates"][0]], outline="cyan")
    out = REPO / "data" / "check" / f"{job_id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    line("6. Picture of the result", True, f"{out.relative_to(REPO)}  (yellow=roof, red=obstacles, cyan=panels, "
                                           "green->red = shade)")
    if open_it and hasattr(os, "startfile"):
        os.startfile(out)  # type: ignore[attr-defined]  # Windows: open in the default image viewer


def s3util_bucket(job: dict) -> str:
    return job["report"]["heatmap_png_s3_uri"].split("/")[2]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lng", type=float)
    ap.add_argument("--address")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--no-job", action="store_true", help="only check the deployment, don't run a job")
    ap.add_argument("--no-open", action="store_true", help="don't open the picture")
    args = ap.parse_args()

    print("SolarRooftop health check\n")
    session = boto3.Session(region_name=REGION)
    try:
        ident = session.client("sts").get_caller_identity()
        line("1. AWS login", True, f"account {ident['Account']}, profile {os.environ.get('AWS_PROFILE', 'default')}")
    except (BotoCoreError, ClientError) as e:
        line("1. AWS login", False, f"{type(e).__name__}. Run:  aws login --profile {os.environ.get('AWS_PROFILE', 'solar')}")
        sys.exit(1)

    check_infra(session)
    if not args.no_job:
        body = ({"address": args.address} if args.address
                else {"lat": args.lat or LAJPAT_NAGAR[0], "lng": args.lng or LAJPAT_NAGAR[1]})
        print(f"5. Live test job: {body}")
        job_id, job = run_job(session, body, args.timeout)
        if job_id:
            try:
                step_timings(session, job_id)
            except (ClientError, StopIteration) as e:
                print(f"   (step timings unavailable: {e})")
        if job and job.get("status") == "done":
            summary(job)
            try:
                picture(session, job_id, job, not args.no_open)
            except Exception as e:  # noqa: BLE001 - the picture is a convenience, not a check
                line("6. Picture of the result", None, f"skipped ({type(e).__name__}: {e})")
    print("\nRESULT:", "ALL GOOD" if failures == 0 else f"{failures} problem(s) - see FAIL lines above")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
