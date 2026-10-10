"""Pack a trained checkpoint into model.tar.gz for SageMaker (files at the archive root -> /opt/ml/model).

Usage (from repo root):
  ml/.venv/bin/python ml/serve/package_model.py --model data/models/segformer_b2_delhi_fp/best --out data/models/package
Then verify it loads exactly like the container will:
  ml/.venv/bin/python ml/serve/package_model.py --verify data/models/package/model.tar.gz
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path

REQUIRED = ["config.json", "model.safetensors"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pack(model_dir: Path, out_dir: Path) -> Path:
    missing = [f for f in REQUIRED if not (model_dir / f).exists()]
    if missing:
        sys.exit(f"{model_dir} is missing {missing}")
    out_dir.mkdir(parents=True, exist_ok=True)
    tar_path = out_dir / "model.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for name in REQUIRED + (["metrics.json"] if (model_dir / "metrics.json").exists() else []):
            tar.add(model_dir / name, arcname=name)
    info = {"source": str(model_dir), "sha256": sha256(tar_path), "bytes": tar_path.stat().st_size}
    (out_dir / "model.tar.gz.json").write_text(json.dumps(info, indent=2))
    print(f"wrote {tar_path} ({info['bytes'] / 1e6:.1f} MB) sha256 {info['sha256'][:16]}…")
    return tar_path


def verify(tar_path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import segment
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(tar_path) as tar:
        names = tar.getnames()
        assert all(n in names for n in REQUIRED), f"archive has {names}"
        assert not any("/" in n for n in names), "files must sit at the archive root"
        tar.extractall(tmp, filter="data")
        model, _ = segment.load_model(tmp, "cpu")
        print(f"ok: {names} load on CPU, {model.config.num_labels} classes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/models/package"))
    ap.add_argument("--verify", type=Path, help="check an existing model.tar.gz")
    args = ap.parse_args()
    if args.verify:
        verify(args.verify)
    elif args.model:
        verify(pack(args.model, args.out))
    else:
        ap.error("give --model or --verify")


if __name__ == "__main__":
    main()
