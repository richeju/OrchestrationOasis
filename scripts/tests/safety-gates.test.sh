#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
roles_path="$repo_root/ansible/playbooks/roles"
localhost_inventory="$repo_root/scripts/tests/fixtures/localhost-inventory.yml"

expect_safe_failure() {
  local playbook=$1
  local expected=$2
  local output
  local status

  set +e
  output=$(ANSIBLE_ROLES_PATH="$roles_path" ansible-playbook \
    --inventory "$localhost_inventory" "$playbook" --check 2>&1)
  status=$?
  set -e

  if [[ $status -eq 0 ]]; then
    printf 'Expected safety failure but playbook succeeded: %s\n' "$playbook" >&2
    return 1
  fi

  if ! grep -Fq "$expected" <<<"$output"; then
    printf 'Expected diagnostic not found in %s:\n%s\n' "$playbook" "$output" >&2
    return 1
  fi
}

expect_safe_failure \
  "$repo_root/scripts/tests/fixtures/yubikey-safety.yml" \
  'Refusing to change SSH authentication'
expect_safe_failure \
  "$repo_root/scripts/tests/fixtures/yubikey-third-party-safety.yml" \
  'active administration user debian must have an enrolled YubiKey'
expect_safe_failure \
  "$repo_root/scripts/tests/fixtures/netbox-secret-safety.yml" \
  'Configure strong NetBox secrets'
expect_safe_failure \
  "$repo_root/scripts/tests/fixtures/prometheus-bind-safety.yml" \
  'Wildcard publication is refused'
expect_safe_failure \
  "$repo_root/scripts/tests/fixtures/prometheus-invalid-bind-safety.yml" \
  'explicit private IPv4 address'
expect_safe_failure \
  "$repo_root/scripts/tests/fixtures/bind-safety.yml" \
  'BIND requires bind_dns_netbox_url and bind_dns_netbox_token'

printf 'safety gate tests passed\n'
