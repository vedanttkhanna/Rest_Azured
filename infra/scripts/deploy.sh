#!/usr/bin/env bash
# Deploy all SolarRooftop stacks, then write web/.env.production for P4.
# Settings come from the repo-root .env (AWS_PROFILE, SOLAR_ALERT_EMAILS, SOLAR_STEP_MODES).
# Usage (Git Bash / Linux / macOS):  infra/scripts/deploy.sh [extra cdk args, e.g. -c web_origins=...]
# Docker Desktop must be running when any step is real.
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$SOLAR_REPO/infra"

: "${SOLAR_ALERT_EMAILS:?set SOLAR_ALERT_EMAILS in .env so budget + failure alerts are kept}"
# Lambda and SageMaker reject images whose manifest carries buildx provenance attestations.
export BUILDX_NO_DEFAULT_ATTESTATIONS=1

modes=()
for m in ${SOLAR_STEP_MODES:-fetch=real segment=real simulate=real}; do modes+=("-c" "$m"); done
echo "step modes: ${SOLAR_STEP_MODES:-fetch=real segment=real simulate=real}"
if [[ " ${SOLAR_STEP_MODES:-real} " == *real* ]] && ! docker info > /dev/null 2>&1; then
  echo "Docker is not running: start Docker Desktop and wait for 'Engine running'." >&2
  exit 1
fi
aws sts get-caller-identity > /dev/null 2>&1 || { echo "AWS login expired: run  aws login --profile ${AWS_PROFILE:-solar}" >&2; exit 1; }

# Synth with the same -c context options (deploy-only flags like --require-approval are not synth options).
ctx=("${modes[@]}"); args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[$i]}" in
    -c|--context) ctx+=("-c" "${args[$((i + 1))]}"); i=$((i + 1)) ;;
    -c=*|--context=*) ctx+=("${args[$i]}") ;;
  esac
done
cdk synth --quiet "${ctx[@]}"
if grep -q '"dockerFile"' cdk.out/*.assets.json 2>/dev/null; then
  python scripts/prebuild_images.py   # Docker v2 manifests for SageMaker (see the script)
fi
cdk deploy --all "${modes[@]}" "$@"
python scripts/export_env.py
