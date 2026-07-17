#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
localhost_inventory="$repo_root/scripts/tests/fixtures/localhost-inventory.yml"
production_vars="$repo_root/ansible/inventories/production/group_vars/restic.yml"
export ANSIBLE_ROLES_PATH="$repo_root/ansible/playbooks/roles"
output_dir=$(mktemp -d)
pycache_dir=$(mktemp -d)
trap 'rm -rf "$output_dir" "$pycache_dir"' EXIT

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
    "/var/backups/infraforge",
}
required_excludes = {
    "/home/debian/OrchestrationOasis/.venv/**",
    "/home/debian/OrchestrationOasis/.trivy-cache/**",
}
assert required_paths <= set(paths)
assert required_excludes <= set(excludes)
assert all(path.rstrip("/") != "/home/debian/infraforge" for path in paths)
for key in (
    "restic_application_backup_enabled",
    "restic_netbox_backup_enabled",
    "restic_authentik_backup_enabled",
    "restic_openbao_backup_enabled",
    "restic_semaphore_backup_enabled",
    "restic_hermes_backup_enabled",
):
    assert config[key] is True
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

set +e
overlap_output=$(ansible-playbook \
  --inventory "$localhost_inventory" \
  "$repo_root/scripts/tests/fixtures/test-restic-overlap-validation.yml" 2>&1)
overlap_status=$?
set -e
[[ $overlap_status -ne 0 ]]
grep -F 'unique, non-overlapping Hermes managed paths' <<< "$overlap_output" >/dev/null

bash -n "$output_dir/restic-backup.sh"
bash -n "$output_dir/restic-backup-audit.sh"
bash -n "$output_dir/restic-application-backup.sh"
bash -n "$output_dir/restic-hermes-restore.sh"
PYTHONPYCACHEPREFIX="$pycache_dir" \
  python3 -m py_compile "$repo_root/scripts/provision-openbao-backup-approle.py"
PYTHONPYCACHEPREFIX="$pycache_dir" \
  python3 "$repo_root/scripts/tests/openbao-backup-approle.test.py"

prepare_line=$(grep -n -F "$output_dir/restic-application-backup.sh" \
  "$output_dir/restic-backup.sh" | cut -d: -f1)
backup_line=$(grep -n -F 'restic backup \' "$output_dir/restic-backup.sh" | cut -d: -f1)
[[ $prepare_line -lt $backup_line ]]
grep -F 'pg_dump --format=custom' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'source.backup(target)' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F '/v1/sys/storage/raft/snapshot' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'OpenBao snapshot checksum mismatch' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'sha256sum -- "${artifacts[@]}"' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F ': >"$stage/COMPLETE"' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'application_backup_incomplete' "$output_dir/restic-backup-audit.sh" >/dev/null
grep -F 'requires the parent backup lock' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'docker stop --time 60' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'docker volume inspect netbox-media-test' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'restart_netbox_writers' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'hermes-state.sqlite3' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'hermes-kanban.sqlite3' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'hermes-files.tar' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'shutil.copy2(source_path, stable_source)' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'source_companion = pathlib.Path' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'systemctl --user --machine=test-hermes@.host \' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'stop test-hermes-gateway.service' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'restart_hermes_gateway' "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'Cannot prove a safe Hermes gateway state' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'hermes_gateway_is_quiescent' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'MainPID' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'ControlPID' \
  "$output_dir/restic-application-backup.sh" >/dev/null
grep -F 'PRAGMA integrity_check' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F '"snapshots", "--host", BACKUP_HOST, "--json"' \
  "$output_dir/restic-backup-audit.sh" >/dev/null
grep -F 'Refusing to restore while the Hermes gateway is active' \
  "$output_dir/restic-hermes-restore.sh" >/dev/null || \
  grep -F 'Refusing production restore without proven quiescent gateway' \
    "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'os.lstat(raw_target)' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'not a symlink' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'canonical_paths=' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'expected_device' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'os.O_NOFOLLOW' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'src_dir_fd=source_parent' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'dst_dir_fd=destination_parent' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'journaled_rename' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'signal.pthread_sigmask' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'Hermes restore generation must be an absolute canonical path' \
  "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'Generation ancestors must be root-owned and non-writable' \
  "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'Overlapping managed Hermes paths are forbidden' \
  "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F '.ROLLBACK_SAFE_TO_CLEAN' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'state.db-wal' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'rollback_path' "$output_dir/restic-hermes-restore.sh" >/dev/null
if grep -F 'rm -rf -- "$target_home/' "$output_dir/restic-hermes-restore.sh" >/dev/null; then
  printf 'Path-based recursive deletion found in Hermes restore transaction.\n' >&2
  exit 1
fi
grep -F 'whatsapp/session/creds.json' "$output_dir/restic-hermes-restore.sh" >/dev/null
grep -F 'kernel/random/uuid' "$output_dir/restic-application-backup.sh" >/dev/null

systemd-analyze verify \
  "$output_dir/restic-backup.service" \
  "$output_dir/restic-backup.timer"

if grep -R -F '{{' "$output_dir" >/dev/null; then
  printf 'Unrendered Jinja expression found in Restic artifact.\n' >&2
  exit 1
fi

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck "$output_dir/restic-backup.sh" \
    "$output_dir/restic-backup-audit.sh" \
    "$output_dir/restic-application-backup.sh"
fi

ansible-playbook \
  --inventory "$repo_root/ansible/inventories/example/hosts.yml" \
  "$repo_root/ansible/playbooks/install_restic.yml" \
  --syntax-check >/dev/null

printf 'Restic role rendering and syntax checks passed.\n'
