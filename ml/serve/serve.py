"""SageMaker inference server (bring-your-own-container) for the rooftop segmentation model.

SageMaker contract: the container is started with the argument `serve`, must answer GET /ping (200 when ready)
and POST /invocations on port 8080. Model files are unpacked from model.tar.gz into /opt/ml/model.

Request (application/json) — contract A fields this step needs:
  {"job_id": "...", "lat": 28.60, "lng": 77.29, "image_bounds": [minLng, minLat, maxLng, maxLat],
   "image_s3_uri": "s3://bucket/jobs/<id>/rgb.png",      # or "image_b64": "<base64 PNG/JPEG/TIFF>" for tests
   "footprint": {GeoJSON Polygon} | null}
Response: contract B JSON (contracts/schemas/B.schema.json). Errors: 400 {"error": "..."}.

Run locally (no Docker):  MODEL_DIR=data/models/segformer_b2_delhi_fp/best ml/.venv/bin/python ml/serve/serve.py serve
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import segment  # noqa: E402

MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/ml/model")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "segformer-b2-delhi-fp-v1")
PORT = int(os.environ.get("SAGEMAKER_BIND_TO_PORT", os.environ.get("PORT", "8080")))
torch.set_num_threads(int(os.environ.get("TORCH_THREADS", str(os.cpu_count() or 2))))

_model = None


def get_model():
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"  # SageMaker Serverless is CPU-only
        _model = segment.load_model(MODEL_DIR, device)
    return _model


def load_image(payload: dict) -> np.ndarray:
    if payload.get("image_b64"):
        data = base64.b64decode(payload["image_b64"])
    elif str(payload.get("image_s3_uri", "")).startswith("s3://"):
        import boto3  # only needed in AWS
        bucket, key = payload["image_s3_uri"][5:].split("/", 1)
        data = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    else:
        raise ValueError("provide image_s3_uri (s3://...) or image_b64")
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.size != (512, 512):
        raise ValueError(f"expected a 512x512 tile centred on the job point, got {img.size}")
    return np.asarray(img)


def handle(payload: dict) -> dict:
    for key in ("job_id", "lat", "lng", "image_bounds"):
        if key not in payload:
            raise ValueError(f"missing field: {key}")
    if len(payload["image_bounds"]) != 4:
        raise ValueError("image_bounds must be [minLng, minLat, maxLng, maxLat]")
    model, device = get_model()
    img = load_image(payload)
    probs = segment.predict_probs(model, device, img)
    return segment.to_contract_b(probs, payload["image_bounds"], float(payload["lat"]), float(payload["lng"]),
                                 str(payload["job_id"]), MODEL_VERSION, payload.get("footprint"), image=img)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/ping":
            try:
                get_model()
                self._send(200, {"status": "ok"})
            except Exception as e:  # noqa: BLE001
                self._send(500, {"error": f"model not loaded: {e}"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/invocations":
            return self._send(404, {"error": "not found"})
        t0 = time.time()
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            result = handle(payload)
            self._send(200, result)
            print(f"invocation job={payload.get('job_id')} features={len(result['features'])} "
                  f"{time.time() - t0:.2f}s", flush=True)
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):  # keep CloudWatch logs to our own lines
        pass


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "serve":
        sys.exit(f"unknown command {sys.argv[1]!r}; SageMaker starts the container with 'serve'")
    get_model()  # load at startup so /ping is fast and cold-start cost is paid once
    print(f"model loaded from {MODEL_DIR}; listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
