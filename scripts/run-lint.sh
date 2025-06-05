#!/bin/bash
# Run yamllint and ansible-lint with project configuration
set -euo pipefail

# Run yamllint using relaxed rules
if command -v yamllint >/dev/null 2>&1; then
    yamllint -d "{extends: relaxed}" .
else
    echo "yamllint is not installed" >&2
fi

# Run ansible-lint using local ansible.cfg
if command -v ansible-lint >/dev/null 2>&1; then
    ANSIBLE_CONFIG=ansible/ansible.cfg ansible-lint "$@"
else
    echo "ansible-lint is not installed" >&2
fi

