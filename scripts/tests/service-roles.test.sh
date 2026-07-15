#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
localhost_inventory="$repo_root/scripts/tests/fixtures/localhost-inventory.yml"
output_dir=$(mktemp -d)
trap 'rm -rf "$output_dir"' EXIT

render() {
  local fixture=$1
  local target=$2
  mkdir -p "$output_dir/$target"
  ansible-playbook --inventory "$localhost_inventory" \
    "$repo_root/scripts/tests/fixtures/$fixture" \
    --extra-vars "repo_root=$repo_root output_dir=$output_dir/$target" >/dev/null
  docker compose -f "$output_dir/$target/compose.yml" config --quiet
}

render render-netbox.yml netbox
python3 -m py_compile "$output_dir/netbox/configuration.py"
grep -Fq "'PASSWORD': os.getenv('REDIS_PASSWORD')" "$output_dir/netbox/configuration.py"
grep -Fq 'requirepass "$$REDIS_PASSWORD"' "$output_dir/netbox/compose.yml"
grep -Fq 'REDIS_PASSWORD=' "$output_dir/netbox/redis.env"

render render-prometheus.yml prometheus
grep -Fq '10.78.0.1:9090:9090' "$output_dir/prometheus/compose.yml"
if grep -Eq '(^|[^0-9])0\.0\.0\.0:9090' "$output_dir/prometheus/compose.yml"; then
  printf 'Prometheus Compose exposes a wildcard port\n' >&2
  exit 1
fi

printf 'service role rendering tests passed\n'
