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

if "$repo_root/scripts/require-ansible-targets.py" \
  --inventory "$repo_root/ansible/inventories/example/hosts.yml" \
  --playbook "$repo_root/ansible/site.yml" >/dev/null 2>&1; then
  printf 'zero-host deployment guard unexpectedly succeeded\n' >&2
  exit 1
fi
"$repo_root/scripts/require-ansible-targets.py" \
  --inventory "$repo_root/ansible/inventories/semaphore-vps.example.yml" \
  --playbook "$repo_root/ansible/playbooks/audit_vps.yml" >/dev/null
"$repo_root/scripts/require-ansible-targets.py" \
  --inventory "$repo_root/scripts/tests/fixtures/hermes-target-inventory.yml" \
  --playbook "$repo_root/ansible/site.yml" --tags hermes >/dev/null

python3 - "$repo_root/.github/workflows/deploy.yml" \
  "$repo_root/.github/workflows/maintenance.yml" <<'PY'
import sys,yaml
workflow=yaml.safe_load(open(sys.argv[1]))
assert workflow['jobs']['deploy']['if'] == "github.ref == 'refs/heads/main'"
options = workflow['on']['workflow_dispatch']['inputs']['target']['options']
assert 'hermes' in options
runs = '\n'.join(
    step.get('run', '') for step in workflow['jobs']['deploy']['steps']
)
assert 'require-ansible-targets.py' in runs
maintenance=yaml.safe_load(open(sys.argv[2]))
maintenance_runs = '\n'.join(
    step.get('run', '') for step in maintenance['jobs']['maintain']['steps']
)
assert maintenance_runs.count('require-ansible-targets.py') == 2
PY

ansible-inventory \
  --inventory "$repo_root/ansible/inventories/semaphore-vps.example.yml" \
  --graph | grep -Fq '@infraforge_vps:'
ansible-playbook "$repo_root/ansible/playbooks/audit_vps.yml" \
  --inventory "$repo_root/ansible/inventories/semaphore-vps.example.yml" \
  --syntax-check >/dev/null

python3 - "$repo_root/Makefile" \
  "$repo_root/ansible/playbooks/docker_cleanup.yml" <<'PY'
import sys
import yaml

makefile = open(sys.argv[1], encoding='utf-8').read()
assert 'check: lint workflows syntax test links' in makefile
assert 'python -m pip_audit --requirement requirements-dev.txt' in makefile
assert './scripts/run-trivy.sh' in makefile

playbook = yaml.safe_load(open(sys.argv[2], encoding='utf-8'))
prune_tasks = [
    task
    for play in playbook
    for task in play.get('tasks', [])
    if 'community.docker.docker_prune' in task
]
assert len(prune_tasks) == 3
assert all('changed_when' not in task for task in prune_tasks)
PY

printf 'repository safety tests passed\n'
