#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export ANSIBLE_CONFIG="$repo_root/ansible/ansible.cfg"

inventory_json=$(ansible-inventory \
  --inventory "$repo_root/ansible/inventories/example/hosts.yml" --list)
python3 -c 'import json,sys; data=json.load(sys.stdin); assert not data.get("_meta", {}).get("hostvars", {}), "default inventory must have zero hosts"' <<<"$inventory_json"

list_hosts=$(ansible-playbook "$repo_root/ansible/site.yml" --list-hosts)
if grep -Fq 'localhost' <<<"$list_hosts"; then
  printf 'default site inventory unexpectedly targets localhost\n' >&2
  exit 1
fi

python3 - "$repo_root/.github/workflows/deploy.yml" <<'PY'
import sys,yaml
workflow=yaml.safe_load(open(sys.argv[1]))
assert workflow['jobs']['deploy']['if'] == "github.ref == 'refs/heads/main'"
PY

ansible-inventory \
  --inventory "$repo_root/ansible/inventories/semaphore-vps.example.yml" \
  --graph | grep -Fq '@infraforge_vps:'
ansible-playbook "$repo_root/ansible/playbooks/audit_vps.yml" \
  --inventory "$repo_root/ansible/inventories/semaphore-vps.example.yml" \
  --syntax-check >/dev/null

printf 'repository safety tests passed\n'
