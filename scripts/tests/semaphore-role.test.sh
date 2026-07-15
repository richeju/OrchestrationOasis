#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export ANSIBLE_ROLES_PATH="$repo_root/ansible/playbooks/roles"
output_dir=$(mktemp -d)
trap 'rm -rf "$output_dir"' EXIT

ansible-playbook \
  --inventory localhost, \
  --extra-vars "test_output_dir=$output_dir" \
  "$repo_root/scripts/tests/fixtures/render-semaphore.yml" >/dev/null

docker compose -f "$output_dir/compose.yml" config --quiet

grep -F '10.78.0.1:3001:3000' "$output_dir/compose.yml" >/dev/null
grep -F 'semaphoreui/semaphore@sha256:' "$output_dir/compose.yml" >/dev/null
grep -F 'no-new-privileges:true' "$output_dir/compose.yml" >/dev/null
grep -F 'read_only: true' "$output_dir/compose.yml" >/dev/null
grep -F 'TMPDIR: /tmp/semaphore' "$output_dir/compose.yml" >/dev/null
grep -F 'PYTHONDONTWRITEBYTECODE: "1"' "$output_dir/compose.yml" >/dev/null
grep -F 'cap_drop:' "$output_dir/compose.yml" >/dev/null
grep -F '/run/semaphore-runner/id_ed25519:ro' "$output_dir/compose.yml" >/dev/null
if grep -F '/var/run/docker.sock' "$output_dir/compose.yml" >/dev/null; then
  printf 'Semaphore must not receive the Docker socket.\n' >&2
  exit 1
fi
if grep -R -F '{{' "$output_dir" >/dev/null; then
  printf 'Unrendered Jinja expression found in Semaphore artifact.\n' >&2
  exit 1
fi

inventory_example="$repo_root/ansible/inventories/semaphore-vps.example.yml"
grep -F 'ansible_connection: ssh' "$inventory_example" >/dev/null
grep -F '/run/semaphore-runner/id_ed25519' "$inventory_example" >/dev/null
grep -F 'StrictHostKeyChecking=yes' "$inventory_example" >/dev/null

ansible-playbook \
  --inventory "$repo_root/ansible/inventories/example/hosts.yml" \
  "$repo_root/ansible/playbooks/install_semaphore.yml" \
  --syntax-check >/dev/null

printf 'Semaphore role rendering and syntax checks passed.\n'
