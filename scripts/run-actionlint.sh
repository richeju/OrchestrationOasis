#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v actionlint >/dev/null 2>&1; then
  actionlint "$repo_root"/.github/workflows/*.yml
  exit 0
fi

docker_command=(docker)
if ! docker info >/dev/null 2>&1; then
  if sudo -n docker info >/dev/null 2>&1; then
    docker_command=(sudo -n docker)
  else
    printf 'actionlint or access to Docker is required to validate workflows\n' >&2
    exit 1
  fi
fi

"${docker_command[@]}" run --rm \
  --volume "$repo_root:/repo:ro" \
  --workdir /repo \
  rhysd/actionlint@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9 \
  .github/workflows/*.yml
