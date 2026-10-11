# Local ML workspace

Run these commands from the repository root. This workspace loads the trained SegFormer checkpoint, predicts roof/obstacle classes, and serves contract-B segmentation results. The web app's normal `cd web && npm run dev` launch uses the checkpoint directly in a complete local P1/P2 job pipeline; `npm run dev:live` uses the deployed P3 API. See [the web launch guide](../web/README.md). The standalone service below is available for P1/P3 integration checks.

## Use the installed environment

```bash
source ml/.venv/bin/activate
python --version
```

This checkout uses Python 3.12.15. The environment and model artifacts are git-ignored. The supplied archive is at `data/models/package/model.tar.gz`, and its unpacked checkpoint is at `data/models/segformer_b2_delhi_fp/best/`.

## Verify the model and tests

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  ml/.venv/bin/python ml/serve/package_model.py --verify data/models/package/model.tar.gz
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  ml/.venv/bin/python -m pytest ml/tests -q
```

The offline flags ensure verification loads local weights. These checks validate CPU loading, contract-B geometry, missing-footprint handling, empty images and serving errors. They do not measure survey accuracy.

## Start the model service

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  MODEL_DIR=data/models/segformer_b2_delhi_fp/best \
  ml/.venv/bin/python ml/serve/serve.py serve
```

The service listens on port 8080. In a second terminal, from the repository root:

```bash
ml/.venv/bin/python ml/serve/invoke.py --url http://localhost:8080
```

This checks `/ping`, sends the public sample tile to `/invocations`, and validates the result against the shared B schema. Stop the service with **Ctrl+C**. Requests can supply an inline base64 image or an S3 image URI; the image must be a centered 512×512 tile. See [the serving guide](serve/README.md) for the request format and P3 deployment handoff.

## Predict your own images

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  ml/.venv/bin/python ml/infer/predict.py \
  --model data/models/segformer_b2_delhi_fp/best \
  --images <folder-of-satellite-tiles> \
  --out data/predictions/my_rooftops
```

Outputs include class-index masks, side-by-side image/segmentation previews and a pixel-share CSV. This batch preview is a class mask; use `ml/serve/segment.py` or the HTTP service to select the target roof and produce WGS84 contract-B polygons. A supplied building footprint helps separate attached roofs.

## Recreate the environment

With `uv` available:

```bash
uv venv ml/.venv --python 3.12
uv pip install --python ml/.venv/bin/python \
  -r ml/requirements.txt -r ml/serve/requirements-serve.txt
uv pip check --python ml/.venv/bin/python
```

Install both requirement files together to retain the tested serving versions while including development/test tools. In this checkout, `uv` was installed locally at `data/tools/bootstrap/bin/uv`, and its Python installation is under `data/python/`. Use the full local `uv` path if it is not on your shell's PATH. The prepared `ml/.venv` commands above already select the correct interpreter.

The local GUI also needs P2's dependencies. Add `-r solar/requirements-dev.txt` to the same installation command. This checkout has the combined ML/serving/solar environment installed and dependency compatibility checked. Installing only the ML requirements does not provide the complete local GUI pipeline.
