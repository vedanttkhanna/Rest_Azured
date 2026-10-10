# AGENTS.md — SolarRooftop AI

Shared, permanent instructions for every coding agent (Claude Code, OpenAI Codex, Google Antigravity) and human on this repo.
Durable knowledge → `PROJECT_CONTEXT.md`. Current progress → `TASKS.md`. Role briefs → `P1_…`–`P4_….md`.

## Operating rules (mandatory for all agents)

1. **Before starting work:** read `AGENTS.md`, `PROJECT_CONTEXT.md`, `TASKS.md`; inspect the code relevant to the task; run `git status` (if the repo is a Git repo) to see uncommitted work.
2. **Before finishing or handing off:** update `PROJECT_CONTEXT.md` (durable knowledge only) and `TASKS.md` (progress) with any meaningful change.
3. **Handoff entries in `TASKS.md` must record:** exact files changed, decisions made, commands executed, *actual* test results (with output summary), unresolved issues, and the single next actionable step.
4. **Never mark incomplete work as complete.** Unverified = "not verified". Untested = "not run".
5. Keep **durable knowledge** (`PROJECT_CONTEXT.md`) separate from **temporary progress** (`TASKS.md`). Move a fact to `PROJECT_CONTEXT.md` only once it will stay true.
6. Don't duplicate what can be read directly from code (signatures, file lists, configs) — link to the file instead.
7. Do not overwrite unrelated user changes or discard uncommitted work. Look before you overwrite.
8. **Do not commit, push, or modify Git history** (commit, amend, rebase, reset, force-push, branch deletion) unless the user explicitly authorizes it in the current session.
9. State facts you verified; label assumptions as assumptions. Don't claim tests pass unless you ran them and they passed.

## Project in one line

Delhi-focused web app: satellite roof image → ML roof/obstacle segmentation → shading + solar energy simulation → kWh / ₹ payback report for homeowners and installers. Built for an AWS hackathon (must be deployed on AWS and/or use an AWS open-source tool).

## Stack (planned — see `PROJECT_CONTEXT.md` for status)

| Area | Owner | Tech |
|---|---|---|
| `ml/` | P1 | PyTorch, SegFormer-B2 / U-Net, SAM 2 (labelling only), SageMaker Serverless Inference |
| `solar/` | P2 | Python, pvlib, PVGIS TMY, rasterio, shapely, pyproj; AWS Lambda container |
| `infra/`, `backend/` | P3 | AWS CDK (Python), API Gateway HTTP API, Lambda, Step Functions, S3, DynamoDB, Cognito, Cedar (`cedarpy`), SSM, CloudWatch, Budgets |
| `web/` | P4 | Vite + React + TypeScript, aws-amplify v6, MapLibre GL, Recharts, TanStack Query, MSW; Amplify Hosting |
| `contracts/` | all | JSON Schemas + fixtures for contracts A (RoofJob), B (Segmentation), C (Report) |

AWS region: `ap-south-1`. **Do not use AWS App Runner** (closed to new customers since 2026-04-30).

## Conventions

- Contracts A/B/C and the HTTP API are defined in the "Shared team contract" section of each `P*.md` brief (identical in all four). Code must validate against `contracts/schemas/` once it exists. **Contract changes require a PR approved by all affected owners.**
- Each directory has one owner (table above). Edit outside your area only when the task requires it, and note it in `TASKS.md`.
- GeoJSON is always WGS84 (EPSG:4326, `[lng, lat]`). All metric computation in UTM 43N (EPSG:32643).
- All tunable constants (heights, prices, subsidies, losses) live in config files, never hard-coded, and are echoed in report `assumptions`.
- Python 3.12; TypeScript strict mode. Scripts that run on the team's Macs must also work on Python 3.9 (macOS system Python): use `from __future__ import annotations`. Read/write text files with `encoding="utf-8"` (Windows defaults to cp1252).
- Datasets, model weights and archives go in `data/` (git-ignored, see `.gitignore`). Never commit data. Raw downloads → `data/raw/`, converted → `data/processed/`.

## Setup & test commands

Run from the repo root. SageMaker build/deploy steps for P3: `ml/serve/README.md`. `ml/` (P1) and `infra/` + `backend/` (P3) exist; other owners add their own verified commands here.

**ml/ (verified 2026-10-10 on Apple M5, macOS):**
```bash
uv venv ml/.venv --python 3.12 && uv pip install --python ml/.venv/bin/python -r ml/requirements.txt
ml/.venv/bin/python ml/data/rid_to_ours.py --rid-data data/raw/RID_m1655470/RID_dataset --out data/processed/rid_ours --fold 1
ml/.venv/bin/python ml/train/train.py --epochs 1 --limit 200 --out data/models/bench   # smoke test (~2 min)
ml/.venv/bin/python ml/data/download_delhi_tiles.py --out data/raw/delhi_tiles --grid 3 --scale 2
ml/.venv/bin/python ml/infer/predict.py --model <checkpoint>/best --images data/raw/delhi_tiles --out data/predictions/<name>
ml/.venv/bin/python ml/data/download_delhi_tiles.py --out data/raw/jobs --center <lat> <lng> --name <job>   # tile centred on a job
ml/.venv/bin/python ml/serve/segment.py --model data/models/segformer_b2_delhi_fp/best --image <tile.png> --lat <lat> --lng <lng> [--footprint fp.json] --out seg_B.json
ml/.venv/bin/python ml/serve/package_model.py --model data/models/segformer_b2_delhi_fp/best --out data/models/package
MODEL_DIR=<unpacked model.tar.gz> ml/.venv/bin/python ml/serve/serve.py serve   # SageMaker server locally, :8080
ml/.venv/bin/python ml/serve/invoke.py --url http://localhost:8080
ml/.venv/bin/python -m pytest ml/tests -q    # 13 tests; model/package tests skip if weights or package missing
```

**infra/ + backend/ + contracts/ tests (P3, verified 2026-10-10 on Windows 11; use `.venv/bin/` on Linux/macOS):**
```bash
uv venv .venv --python 3.12 && uv pip install --python .venv/Scripts/python.exe -r infra/requirements-dev.txt
.venv/Scripts/ruff.exe check backend infra contracts
.venv/Scripts/python.exe -m pytest backend/tests infra/tests contracts/tests -q    # 74 tests, no AWS needed (moto)
cd infra && PATH="$PWD/../.venv/Scripts:$PATH" cdk synth --quiet                 # needs Node + `npm i -g aws-cdk`
```
Deploy / smoke / teardown (P3 only, needs AWS credentials): see `infra/README.md` — **not yet run**.

## Constraints

- Budget: ~$200 AWS credits. No provisioned GPU endpoints unless the team agrees; delete same day. Train models off-AWS (Kaggle/Colab/local).
- Only P3 deploys to AWS.
- Lambda/serverless inference limits: aim < 60 s per step.

## Security

- No secrets, API keys, or `.env*` files in the repo. Google API key → SSM Parameter Store SecureString.
- Least-privilege IAM per function; S3 private, access via presigned URLs only.
- Authorization via Cognito groups (`Homeowner`, `Installer`) + Cedar policies; enforce in the API, not only in the UI.
- Never send user addresses or personal data to services other than those listed in the stack.
