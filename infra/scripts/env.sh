# Sourced by the other infra/scripts/*.sh: loads the repo-root .env and puts aws, docker and the venv on PATH.
# Also usable in your own terminal:  source infra/scripts/env.sh
SOLAR_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ -f "$SOLAR_REPO/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . <(sed 's/\r$//' "$SOLAR_REPO/.env")
  set +a
fi
export AWS_REGION="${AWS_REGION:-ap-south-1}" AWS_DEFAULT_REGION="${AWS_REGION:-ap-south-1}"
for d in "/c/Program Files/Amazon/AWSCLIV2" "/c/Program Files/Docker/Docker/resources/bin"; do
  [ -d "$d" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
if [ -d "$SOLAR_REPO/.venv/Scripts" ]; then PATH="$SOLAR_REPO/.venv/Scripts:$PATH"; else PATH="$SOLAR_REPO/.venv/bin:$PATH"; fi
export PATH
