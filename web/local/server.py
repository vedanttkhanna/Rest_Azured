"""Loopback-only development job API using the real P1/P2 pipeline.

No fixture results, AWS deployment, or shared-contract changes. Run via npm run dev.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "solar"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from solar.config import load_config
from solar.fetch import fetch_job
from solar.geo import check_location
from solar.providers import ProviderError
from solar.report import simulate
from solar.storage import Store


def now():
    return datetime.now(timezone.utc).isoformat()


class Pipeline:
    def __init__(self, settings):
        import torch
        from ml.serve.segment import load_model

        self.settings = settings
        self.config = load_config()
        self.store = Store(ROOT / settings["workspace"])
        torch.set_num_threads(settings["torch_threads"])
        self.model, self.device = load_model(ROOT / settings["model_dir"], "cpu")

    def fetch(self, job):
        # Public Esri imagery + Overture context; Google credentials are optional
        # in the deployed pipeline and are not required for this local path.
        return fetch_job({**job, "provider": "esri"}, self.store, self.config)

    def segment(self, job):
        import numpy as np
        import rasterio
        from PIL import Image
        from ml.serve.segment import predict_probs, to_contract_b

        with rasterio.open(job["image_s3_uri"]) as source:
            image = np.moveaxis(source.read([1, 2, 3]), 0, -1)
        Image.fromarray(image).save(self.store.path(f"jobs/{job['job_id']}/rgb.png"))
        result = to_contract_b(
            predict_probs(self.model, self.device, image), job["image_bounds"],
            job["lat"], job["lng"], job["job_id"], self.settings["model_version"],
            job.get("footprint"), image=image,
        )
        self.store.put_json(f"jobs/{job['job_id']}/seg_B.json", result)
        return result

    def simulate(self, job, segmentation):
        return simulate(job, segmentation, self.store, self.config)


class Jobs:
    def __init__(self, pipeline, settings, geocoder=None):
        self.pipeline, self.settings = pipeline, settings
        self.root = pipeline.store.root
        self.geocoder = geocoder
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rooftop")
        self.index = self.root / "index.json"
        self.jobs = json.loads(self.index.read_text(encoding="utf-8")) if self.index.exists() else {}
        # A stopped local process cannot finish its queued work. Keep completed
        # reports and turn interrupted jobs into explicit failures on restart.
        for job in self.jobs.values():
            if job["status"] not in ("done", "failed"):
                job.update(status="failed", error="Local service stopped during this assessment. Please try again.", updated_at=now())
        self.save()

    def save(self):
        with self.lock:
            temp = self.index.with_suffix(".tmp")
            temp.write_text(json.dumps(self.jobs, allow_nan=False), encoding="utf-8")
            temp.replace(self.index)

    def resolve(self, value):
        if isinstance(value, str):
            value = {"address": value}
        if not isinstance(value, dict):
            raise ValueError("Use an address or numeric lat/lng coordinates.")
        address = value.get("address", "")
        if not isinstance(address, str) or len(address) > 500:
            raise ValueError("Address must be text with at most 500 characters.")
        if "lat" in value or "lng" in value:
            lat, lng = check_location(value.get("lat"), value.get("lng"), self.pipeline.config)
        else:
            if not address.strip():
                raise ValueError("Select a rooftop on the map or enter an address.")
            if self.geocoder is None:
                raise ValueError("Local address lookup needs AWS credentials. Use the map pin or latitude/longitude instead.")
            location = self.geocoder(address.strip())
            lat, lng = check_location(location["lat"], location["lng"], self.pipeline.config)
            address = location.get("label", address)
        return {"lat": lat, "lng": lng, "address": address.strip() or f"Rooftop at {lat:.6f}, {lng:.6f}"}

    def create(self, location):
        jid = str(uuid.uuid4())
        with self.lock:
            self.jobs[jid] = {"job_id": jid, **location, "status": "queued", "created_at": now(), "updated_at": now()}
            self.save()
        self.executor.submit(self.run, jid)
        return jid

    def update(self, jid, **values):
        with self.lock:
            self.jobs[jid].update(values, updated_at=now())
            self.save()

    def get(self, jid):
        with self.lock:
            return copy.deepcopy(self.jobs.get(jid))

    def summaries(self):
        with self.lock:
            return sorted(
                [{k: v for k, v in job.items() if k not in ("report", "segmentation", "heatmap_png_url", "image_png_url", "image_bounds")}
                 for job in self.jobs.values()],
                key=lambda job: job["created_at"], reverse=True,
            )

    def run(self, jid):
        stage = "fetching"
        try:
            self.update(jid, status=stage)
            job = self.pipeline.fetch(self.get(jid))
            self.update(jid, image_bounds=job["image_bounds"])
            stage = "segmenting"
            self.update(jid, status=stage)
            segmentation = self.pipeline.segment(job)
            if not any(f["properties"]["kind"] == "roof" for f in segmentation["features"]):
                raise ValueError("No roof was detected at this pin. Move the pin to the center of a visible rooftop and try again.")
            stage = "simulating"
            self.update(jid, status=stage)
            report = self.pipeline.simulate(job, segmentation)
            self.update(jid, status="done", report=report, segmentation=segmentation,
                        heatmap_png_url=f"/api/assets/{jid}/shade.png", image_png_url=f"/api/assets/{jid}/rgb.png",
                        kw_dc=report["system"]["kw_dc"], annual_kwh=report["energy"]["annual_kwh"],
                        payback_years=report["finance"]["payback_years"])
            print(f"done {jid}: {report['system']['panel_count']} panels, {report['energy']['annual_kwh']:.1f} kWh/year", flush=True)
        except (ValueError, ProviderError) as exc:
            self.update(jid, status="failed", error=f"{stage.capitalize()}: {exc}")
            print(f"failed {jid} during {stage}: {type(exc).__name__}", flush=True)
        except Exception as exc:
            # No upstream URLs, credentials, addresses or raw exception bodies
            # enter the UI/logs. Failures never return a canned fixture report.
            self.update(jid, status="failed", error=f"{stage.capitalize()} could not finish ({type(exc).__name__}). Check the network connection and retry.")
            print(f"failed {jid} during {stage}: {type(exc).__name__}", flush=True)


def make_handler(jobs):
    class Handler(BaseHTTPRequestHandler):
        def allowed(self):
            host = urlparse("http://" + self.headers.get("Host", "")).hostname
            origin = self.headers.get("Origin")
            return host in ("localhost", "127.0.0.1") and (not origin or origin in ("http://localhost:5173", "http://127.0.0.1:5173"))

        def send(self, code, body):
            data = json.dumps(body, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.write_bytes(data)

        def write_bytes(self, data):
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Navigating away can cancel a map image or polling request.

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {"error": "This API is only available in the local workspace."})
            path = urlparse(self.path).path
            if path == "/health":
                return self.send(200, {"status": "ok", "mode": "local", "geocoding": jobs.geocoder is not None,
                                       "model_version": jobs.settings["model_version"]})
            if path == "/jobs":
                return self.send(200, {"jobs": jobs.summaries()})
            if path.startswith("/jobs/"):
                job = jobs.get(path.removeprefix("/jobs/"))
                return self.send(200, job) if job else self.send(404, {"error": "Job not found."})
            match = re.fullmatch(r"/assets/([a-f0-9-]{36})/(shade\.png|rgb\.png)", path)
            if match and jobs.get(match[1]):
                file = jobs.root / "jobs" / match[1] / match[2]
                if file.is_file():
                    data = file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.write_bytes(data)
                    return
            self.send(404, {"error": "Not found."})

        def do_POST(self):
            if not self.allowed():
                return self.send(403, {"error": "This API is only available in the local workspace."})
            path = urlparse(self.path).path
            if path not in ("/jobs", "/jobs/batch"):
                return self.send(404, {"error": "Not found."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= jobs.settings["max_request_bytes"]:
                    return self.send(413, {"error": "Request is empty or too large."})
                body = json.loads(self.rfile.read(length))
                if path == "/jobs":
                    return self.send(201, {"job_id": jobs.create(jobs.resolve(body))})
                if self.headers.get("X-Local-Role") != "Installer":
                    return self.send(403, {"error": "Batch assessments are available to Installer workspaces only."})
                inputs = body.get("addresses") if isinstance(body, dict) else None
                if not isinstance(inputs, list) or not 1 <= len(inputs) <= jobs.settings["max_batch"]:
                    raise ValueError(f"Add 1–{jobs.settings['max_batch']} locations.")
                locations, invalid = [], []
                for index, value in enumerate(inputs):
                    try:
                        locations.append(jobs.resolve(value))
                    except (ValueError, TypeError) as exc:
                        invalid.append({"index": index, "input": value, "error": str(exc)})
                if invalid:
                    return self.send(400, {"error": "Some entries are invalid; nothing was created.", "invalid": invalid})
                self.send(201, {"job_ids": [jobs.create(location) for location in locations]})
            except json.JSONDecodeError:
                self.send(400, {"error": "Invalid JSON request."})
            except ValueError as exc:
                self.send(400, {"error": str(exc)})
            except TypeError:
                self.send(400, {"error": "Use numeric latitude/longitude within Delhi/NCR."})

        def log_message(self, *_args):
            pass
    return Handler


def make_geocoder(session):
    """Address lookup through P3's Amazon Location adapter, or None when AWS credentials are unusable.

    Loading credentials can raise (e.g. `aws login` credentials need the optional botocore[crt] package,
    or an expired session). Address lookup is optional, so any such failure disables it instead of
    stopping the local workspace; pins and coordinates never need AWS.
    """
    try:
        credentials = session.get_credentials()
    except Exception as exc:  # noqa: BLE001 - any credential problem only disables address lookup
        print(f"Address lookup disabled: AWS credentials could not be loaded ({type(exc).__name__}: {exc})", flush=True)
        return None
    if credentials is None:
        return None
    from backend.api import geocode
    geocode._client = session.client("geo-places")

    def geocoder(address):
        try:
            return geocode.geocode(address)
        except Exception:
            raise ValueError("AWS address lookup failed. Use an exact map pin or coordinates.") from None
    return geocoder


def main():
    settings = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=settings["port"])
    args = parser.parse_args()
    import boto3
    geocoder = make_geocoder(boto3.Session(region_name=settings["region"]))
    pipeline = Pipeline(settings)
    jobs = Jobs(pipeline, settings, geocoder)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(jobs))
    print(f"Real local rooftop API ready at http://127.0.0.1:{args.port}; address lookup {'enabled' if geocoder else 'needs AWS credentials'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        jobs.executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
