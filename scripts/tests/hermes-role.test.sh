#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
localhost_inventory="$repo_root/scripts/tests/fixtures/localhost-inventory.yml"
production_vars="$repo_root/ansible/inventories/production/group_vars/hermes.yml"
output_dir=$(mktemp -d)
trap 'rm -rf "$output_dir"' EXIT
export ANSIBLE_ROLES_PATH="$repo_root/ansible/playbooks/roles"

python3 - "$repo_root" "$production_vars" <<'PY'
import pathlib
import sys
import yaml

root = pathlib.Path(sys.argv[1])
production = yaml.safe_load(pathlib.Path(sys.argv[2]).read_text())
defaults = yaml.safe_load(
    (root / "ansible/playbooks/roles/hermes/defaults/main.yml").read_text()
)
assert defaults["hermes_manage_installation"] is False
assert defaults["hermes_migrate_config"] is False
assert defaults["hermes_install_commit"] == ""
assert defaults["hermes_allow_checkout_replacement"] is False
assert defaults["hermes_installer_checksum"].startswith("sha256:")
assert "/e0240d7bf7ce0d665417d45de0bfa9a65cb0ab48/" in defaults["hermes_installer_url"]
assert production["hermes_user"] == "debian"
assert production["hermes_manage_installation"] is False
for key in defaults:
    lowered = key.lower()
    assert not any(word in lowered for word in ("password", "secret", "api_key", "token")), key
PY

ansible-playbook --inventory "$localhost_inventory" \
  "$repo_root/scripts/tests/fixtures/render-hermes.yml" \
  --extra-vars "repo_root=$repo_root test_output_dir=$output_dir hermes_home=$output_dir/test-hermes hermes_install_dir=$output_dir/test-hermes/hermes-agent" >/dev/null

systemd-analyze verify "$output_dir/hermes-gateway.service"
dropin="$output_dir/hermes-gateway.service.d/infraforge-hardening.conf"
grep -F 'UMask=0077' "$dropin" >/dev/null
if grep -Eiq 'password|secret|api[_-]?key|token' "$dropin"; then
  printf 'Hermes gateway drop-in must not contain secrets\n' >&2
  exit 1
fi

ansible-playbook --syntax-check --inventory "$localhost_inventory" \
  "$repo_root/ansible/playbooks/install_hermes.yml" >/dev/null

grep -F -- '--non-interactive' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/install.yml" >/dev/null
grep -F -- '--skip-setup' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/install.yml" >/dev/null
grep -F 'hermes_install_commit' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/install.yml" >/dev/null
grep -F 'not (hermes_binary_usable | bool)' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/install.yml" >/dev/null
grep -F 'mode: "0750"' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/install.yml" >/dev/null
grep -F 'mode: "0550"' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/install.yml" >/dev/null
grep -F 'ansible_check_mode and not (hermes_binary_usable | bool)' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/main.yml" >/dev/null
grep -F 'loginctl' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/gateway.yml" >/dev/null
grep -F 'ansible.builtin.systemd_service:' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/gateway.yml" >/dev/null
grep -F 'scope: user' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/gateway.yml" >/dev/null
grep -F 'XDG_RUNTIME_DIR:' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/gateway.yml" >/dev/null
grep -F 'config check' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/verify.yml" >/dev/null
grep -F 'gateway status --deep' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/verify.yml" >/dev/null
grep -F 'hermes_gateway_started | bool' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/verify.yml" >/dev/null
grep -F 'hermes_manage_gateway | bool' \
  "$repo_root/ansible/playbooks/roles/hermes/handlers/main.yml" >/dev/null
grep -F 'hermes_gateway_started | bool' \
  "$repo_root/ansible/playbooks/roles/hermes/handlers/main.yml" >/dev/null
grep -F 'mode: "0600"' \
  "$repo_root/ansible/playbooks/roles/hermes/tasks/state.yml" >/dev/null
grep -F 'install_hermes.yml' "$repo_root/ansible/site.yml" >/dev/null
grep -F 'hermes:' "$repo_root/ansible/inventories/example/hosts.yml" >/dev/null

printf 'Hermes role rendering and safety checks passed.\n'
