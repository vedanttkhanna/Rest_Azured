# Roof segmentation service — SageMaker hand-off (P1 → P3)

Custom container (BYOC) for **SageMaker Serverless Inference** (CPU). Input: a 512×512 tile centred on the job point. Output: contract B (`contracts/schemas/B.schema.json`).

## What's here
| File | Purpose |
|---|---|
| `serve.py` | HTTP server SageMaker talks to: `GET /ping`, `POST /invocations` on port 8080 |
| `segment.py` | Model inference + post-processing → contract B |
| `Dockerfile`, `requirements-serve.txt` | Container (python:3.12-slim, CPU-only torch, pinned versions) |
| `package_model.py` | Builds and checks `model.tar.gz` (weights at archive root) |
| `invoke.py` | Sends the `contracts/fixtures` job to a local server or a deployed endpoint and validates the reply |

## Verified locally (2026-10-10, Apple M5, no Docker)
- `model.tar.gz`: 101.6 MB, loads on CPU from an unpacked copy (as `/opt/ml/model`).
- Server run exactly as in the container (`serve.py serve`, `MODEL_DIR` = unpacked package, offline, CPU): `/ping` 200; fixture request → valid contract B in **~0.8 s** round trip; 2 concurrent requests ~1.3 s each; bad input → HTTP 400 with a message; **RSS ~1.5 GB**.
- `ml/.venv/bin/python -m pytest ml/tests -q` → 13 passed.
- **Not verified:** the Docker image build, x86_64 behaviour, S3 image download (`image_s3_uri`), and anything on AWS. No Docker/Finch or AWS CLI on the P1 machine.

## Request / response
```json
POST /invocations   Content-Type: application/json
{ "job_id": "uuid", "lat": 28.6039825, "lng": 77.2935395,
  "image_bounds": [77.2931962, 28.603681, 77.2938828, 28.6042839],
  "image_s3_uri": "s3://<jobs-bucket>/jobs/<job_id>/rgb.png",
  "footprint": { "type": "Polygon", "coordinates": [...] } }
```
- `image_b64` (base64 PNG) can replace `image_s3_uri` for testing.
- `footprint` is optional but **strongly recommended**. Without it the roof is capped to 12 m around the point and `warning` is set (Delhi row houses share walls).
- Response: contract B JSON (see `contracts/fixtures/seg_B.json`). Errors return 400 or 500 with `{"error": "..."}`.

## Build, push, deploy (P3)
Run from the repo root. Docker or Finch works (`finch` takes the same arguments as `docker`).
```bash
# 1. model package -> S3
ml/.venv/bin/python ml/serve/package_model.py --model data/models/segformer_b2_delhi_fp/best --out data/models/package
aws s3 cp data/models/package/model.tar.gz s3://<model-bucket>/segformer-b2-delhi-fp-v1/model.tar.gz

# 2. image -> ECR (x86_64 for Serverless)
aws ecr create-repository --repository-name solarrooftop-seg --region ap-south-1
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <acct>.dkr.ecr.ap-south-1.amazonaws.com
docker build --platform linux/amd64 -f ml/serve/Dockerfile -t solarrooftop-seg:v1 .
docker tag solarrooftop-seg:v1 <acct>.dkr.ecr.ap-south-1.amazonaws.com/solarrooftop-seg:v1
docker push <acct>.dkr.ecr.ap-south-1.amazonaws.com/solarrooftop-seg:v1

# 3. optional local container test before deploying
mkdir -p /tmp/opt_ml_model && tar -xzf data/models/package/model.tar.gz -C /tmp/opt_ml_model
docker run --rm -p 8080:8080 -v /tmp/opt_ml_model:/opt/ml/model solarrooftop-seg:v1 serve
ml/.venv/bin/python ml/serve/invoke.py --url http://localhost:8080
```
SageMaker resources (CDK or console):
- **Model**: image = the ECR URI above, `ModelDataUrl` = the S3 `model.tar.gz`, env `MODEL_VERSION=segformer-b2-delhi-fp-v1`.
- **Execution role**:
  - ECR pull and CloudWatch Logs;
  - `s3:GetObject` on the model object and on `jobs/*` in the jobs bucket.
- **EndpointConfig**: `ServerlessConfig {MemorySizeInMB: 4096, MaxConcurrency: 2}`. 4 GB leaves headroom over the ~1.5 GB used; raise to 6144 if latency is too high, since Serverless gives more CPU with more memory.
- **Endpoint**: e.g. `solarrooftop-seg`. Then test it:
  `ml/.venv/bin/python ml/serve/invoke.py --endpoint solarrooftop-seg --region ap-south-1`.
- Check that SageMaker Serverless Inference is available in `ap-south-1` before relying on it (not verified).

## Cost notes
Serverless costs nothing while idle. Expect a cold start after idle periods: the image pull plus process start-up. Locally, Python imports took ~1.4 s and loading the weights <0.1 s (warm disk cache, Apple M5); the AWS cold-start time has not been measured. Don't create a provisioned GPU endpoint for this model; CPU is fast enough.
