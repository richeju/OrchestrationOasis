#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
trivy_image='aquasec/trivy@sha256:cffe3f5161a47a6823fbd23d985795b3ed72a4c806da4c4df16266c02accdd6f'
cache_volume='orchestration-oasis-trivy-cache'

docker_command=(docker)
if ! docker info >/dev/null 2>&1; then
  if sudo -n docker info >/dev/null 2>&1; then
    docker_command=(sudo -n docker)
  else
    printf 'Docker daemon access is required (directly or through passwordless sudo).\n' >&2
    exit 1
  fi
fi

"${docker_command[@]}" run --rm \
  --volume "$repo_root:/project:ro" \
  --volume "$cache_volume:/root/.cache" \
  "$trivy_image" fs \
  --scanners vuln,misconfig,secret \
  --ignore-unfixed \
  --exit-code 1 \
  --severity HIGH,CRITICAL \
  --skip-dirs .venv \
  --skip-dirs .git \
  --skip-dirs .trivy-cache \
  /project
