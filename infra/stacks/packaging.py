"""Build zip-Lambda asset folders at synth time without Docker.

Each asset = selected source files/folders copied into infra/.build/<name>/ plus Linux x86_64 wheels for the
Lambda's requirements, installed with `uv pip install --target ... --python-platform x86_64-manylinux2014`.
Installed dependencies are cached per requirements-file hash in infra/.build/deps/.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "infra" / ".build"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "requirements.txt")


def _install_deps(requirements: Path) -> Path:
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()[:16]
    target = BUILD / "deps" / digest
    if target.is_dir():
        return target
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("`uv` is needed to package Lambda dependencies (https://docs.astral.sh/uv/)")
    tmp = target.with_suffix(".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    subprocess.run([uv, "pip", "install", "--quiet", "--target", str(tmp), "--python-platform", "x86_64-manylinux2014",
                    "--python-version", "3.12", "--only-binary", ":all:", "-r", str(requirements)], check=True)
    tmp.rename(target)
    return target


def python_asset(name: str, sources: dict[str, Path], requirements: Path | None = None) -> str:
    """sources maps destination path inside the asset -> source file or folder (absolute or repo-relative)."""
    out = BUILD / name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    if requirements is not None:
        shutil.copytree(_install_deps(REPO / requirements), out, dirs_exist_ok=True)
    for dest, src in sources.items():
        src = REPO / src
        if src.is_dir():
            shutil.copytree(src, out / dest, ignore=_IGNORE, dirs_exist_ok=True)
        else:
            (out / dest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out / dest)
    return str(out)
