#!/usr/bin/env bash
# Deploy all SolarRooftop stacks, then write web/.env.production for P4.
# Usage (Git Bash / Linux / macOS, from anywhere):
#   export AWS_PROFILE=solar SOLAR_ALERT_EMAILS=a@x.com,b@y.com
#   infra/scripts/deploy.sh                      # all steps stubbed
#   infra/scripts/deploy.sh -c segment=real      # P1's SageMaker endpoint (needs Docker Desktop running)
set -euo pipefail
cd "$(dirname "$0")/.."

: "${SOLAR_ALERT_EMAILS:?set SOLAR_ALERT_EMAILS=a@x.com,b@y.com so budget + failure alerts are created}"
export AWS_REGION=ap-south-1 AWS_DEFAULT_REGION=ap-south-1
# Lambda and SageMaker reject images whose manifest carries buildx provenance attestations.
export BUILDX_NO_DEFAULT_ATTESTATIONS=1

if [ -d ../.venv/Scripts ]; then export PATH="$PWD/../.venv/Scripts:$PATH"; else export PATH="$PWD/../.venv/bin:$PATH"; fi

# Synth with the same -c context options (deploy-only flags like --require-approval are not synth options).
ctx=(); args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[$i]}" in
    -c|--context) ctx+=("-c" "${args[$((i + 1))]}"); i=$((i + 1)) ;;
    -c=*|--context=*) ctx+=("${args[$i]}") ;;
  esac
done
cdk synth --quiet "${ctx[@]}"
if grep -q '"dockerImages": {' cdk.out/*.assets.json 2>/dev/null && grep -q '"dockerFile"' cdk.out/*.assets.json; then
  python scripts/prebuild_images.py   # Docker v2 manifests for SageMaker (see the script)
fi
cdk deploy --all "$@"
python scripts/export_env.py
