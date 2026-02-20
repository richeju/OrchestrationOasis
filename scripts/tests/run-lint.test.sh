#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/run-lint.sh"

assert_contains() {
    local haystack="$1"
    local needle="$2"

    if [[ "$haystack" != *"$needle"* ]]; then
        echo "Assertion failed: expected output to contain '$needle'"
        echo "Actual output:"
        printf '%s\n' "$haystack"
        exit 1
    fi
}

test_fails_when_lint_tools_are_missing() {
    local temp_path
    temp_path="$(mktemp -d)"

    set +e
    local output
    output="$(PATH="$temp_path" "$SCRIPT" 2>&1)"
    local exit_code=$?
    set -e

    rm -rf "$temp_path"

    if [ "$exit_code" -eq 0 ]; then
        echo "Expected non-zero exit code when lint tools are missing"
        exit 1
    fi

    assert_contains "$output" "yamllint is not installed"
    assert_contains "$output" "ansible-lint is not installed"
}

test_runs_both_linters_when_available() {
    local temp_path
    temp_path="$(mktemp -d)"

    cat > "$temp_path/yamllint" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "yamllint:$*"
SH

    cat > "$temp_path/ansible-lint" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "ansible-lint:$*|ANSIBLE_CONFIG=${ANSIBLE_CONFIG:-unset}"
SH

    chmod +x "$temp_path/yamllint" "$temp_path/ansible-lint"

    local output
    output="$(PATH="$temp_path:$PATH" "$SCRIPT" --offline 2>&1)"

    rm -rf "$temp_path"

    assert_contains "$output" "yamllint:-d {extends: relaxed} ."
    assert_contains "$output" "ansible-lint:--offline|ANSIBLE_CONFIG=ansible/ansible.cfg"
}

test_fails_when_lint_tools_are_missing
test_runs_both_linters_when_available

echo "run-lint tests passed"
