"""Pre-build CDK's container image assets with Docker v2 manifests (called by deploy.sh after `cdk synth`).

Docker Desktop's containerd image store makes `docker build` produce OCI manifests, which SageMaker rejects
("Unsupported manifest media type application/vnd.oci.image.manifest.v1+json"). CDK's `outputs` option would fix
that, but CDK CLI 2.1145 crashes on it ("x.replace is not a function"). CDK skips its own build when the local tag
`cdkasset-<asset id>` already exists, so we build that tag here with `oci-mediatypes=false` and CDK just pushes it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

CDK_OUT = Path(__file__).resolve().parents[1] / "cdk.out"


def main() -> None:
    docker = shutil.which("docker")
    if docker is None:
        sys.exit("docker not found on PATH (start Docker Desktop / open a new terminal)")
    for manifest in sorted(CDK_OUT.glob("*.assets.json")):
        for asset_id, image in json.loads(manifest.read_text(encoding="utf-8")).get("dockerImages", {}).items():
            src = image["source"]
            tag = f"cdkasset-{asset_id}"
            if subprocess.run([docker, "image", "inspect", tag], capture_output=True).returncode == 0:
                print(f"[prebuild] {src.get('dockerFile')}: {tag} already built")
                continue
            cmd = [docker, "build", "--provenance=false", "--output", "type=docker,oci-mediatypes=false",
                   "--tag", tag, "--file", src.get("dockerFile", "Dockerfile")]
            if src.get("platform"):
                cmd += ["--platform", src["platform"]]
            print(f"[prebuild] {src.get('dockerFile')} -> {tag}", flush=True)
            subprocess.run([*cmd, "."], cwd=CDK_OUT / src["directory"], check=True)


if __name__ == "__main__":
    main()
