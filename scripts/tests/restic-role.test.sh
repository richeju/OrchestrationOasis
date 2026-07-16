#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
localhost_inventory="$repo_root/scripts/tests/fixtures/localhost-inventory.yml"
production_vars="$repo_root/ansible/inventories/production/group_vars/restic.yml"
export ANSIBLE_ROLES_PATH="$repo_root/ansible/playbooks/roles"
output_dir=$(mktemp -d)
trap 'rm -rf "$output_dir"' EXIT

python3 - "$production_vars" <<'PY'
import sys
import yaml

config = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
paths = config["restic_backup_paths"]
excludes = config["restic_exclude_patterns"]
required_paths = {
    "/home/debian/OrchestrationOasis",
    "/home/debian/.semaphore",
    "/home/debian/semaphore",
}
required_excludes = {
    "/home/debian/OrchestrationOasis/.venv/**",
    "/home/debian/OrchestrationOasis/.trivy-cache/**",
}
assert required_paths <= set(paths)
assert required_excludes <= set(excludes)
assert all(path.rstrip("/") != "/home/debian/infraforge" for path in paths)
PY

ansible-playbook \
  --inventory "$localhost_inventory" \
  --extra-vars "test_output_dir=$output_dir" \
  "$repo_root/scripts/tests/fixtures/render-restic.yml" >/dev/null

expected_repository='rclone:test-remote:Backups/path with # and $(touch '"$output_dir"'/injected)'
expected_password_file="$output_dir/password file 'quoted'"
expected_rclone_config="$output_dir/rclone config #1"
expected_cache_dir="$output_dir/cache with spaces"
expected_host="host with 'quote' and "'$dollar'
actual_repository=$(bash -c 'source "$1"; printf "%s" "$RESTIC_REPOSITORY"' _ "$output_dir/restic.env")
actual_password_file=$(bash -c 'source "$1"; printf "%s" "$RESTIC_PASSWORD_FILE"' _ "$output_dir/restic.env")
actual_rclone_config=$(bash -c 'source "$1"; printf "%s" "$RCLONE_CONFIG"' _ "$output_dir/restic.env")
actual_cache_dir=$(bash -c 'source "$1"; printf "%s" "$RESTIC_CACHE_DIR"' _ "$output_dir/restic.env")
actual_host=$(bash -c 'source "$1"; printf "%s" "$RESTIC_HOST"' _ "$output_dir/restic.env")
[[ $actual_repository == "$expected_repository" ]]
[[ $actual_password_file == "$expected_password_file" ]]
[[ $actual_rclone_config == "$expected_rclone_config" ]]
[[ $actual_cache_dir == "$expected_cache_dir" ]]
[[ $actual_host == "$expected_host" ]]
[[ ! -e "$output_dir/injected" ]]

printf 'original-password-file-content\n' >"$output_dir/existing.pass"
chmod 0600 "$output_dir/existing.pass"

ansible-playbook \
  --inventory "$localhost_inventory" \
  --extra-vars "test_output_dir=$output_dir" \
  --check \
  "$repo_root/scripts/tests/fixtures/test-restic-password.yml" >/dev/null

ansible-playbook \
  --inventory "$localhost_inventory" \
  --extra-vars "test_output_dir=$output_dir" \
  "$repo_root/scripts/tests/fixtures/test-restic-password.yml" >/dev/null

ansible-playbook \
  --inventory "$localhost_inventory" \
  "$repo_root/scripts/tests/fixtures/test-restic-validation.yml" >/dev/null

bash -n "$output_dir/restic-backup.sh"
bash -n "$output_dir/restic-backup-audit.sh"

systemd-analyze verify \
  "$output_dir/restic-backup.service" \
  "$output_dir/restic-backup.timer"

if grep -R -F '{{' "$output_dir" >/dev/null; then
  printf 'Unrendered Jinja expression found in Restic artifact.\n' >&2
  exit 1
fi

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck "$output_dir/restic-backup.sh" "$output_dir/restic-backup-audit.sh"
fi

ansible-playbook \
  --inventory "$repo_root/ansible/inventories/example/hosts.yml" \
  "$repo_root/ansible/playbooks/install_restic.yml" \
  --syntax-check >/dev/null

printf 'Restic role rendering and syntax checks passed.\n'
