#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
roles_path="$repo_root/ansible/playbooks/roles"

expect_safe_failure() {
  local playbook=$1
  local expected=$2
  local output
  local status

  set +e
  output=$(ANSIBLE_ROLES_PATH="$roles_path" ansible-playbook \
    --inventory localhost, --connection local "$playbook" --check 2>&1)
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
  "$repo_root/scripts/tests/fixtures/bind-safety.yml" \
  'BIND requires bind_dns_netbox_url and bind_dns_netbox_token'

printf 'safety gate tests passed\n'
