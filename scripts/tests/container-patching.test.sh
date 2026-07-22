#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
mkdir -p "$tmpdir/stack"

export PATCHING_LIB_ONLY=1
# shellcheck source=../sunday-container-patching.sh
source "$repo_root/scripts/sunday-container-patching.sh"

HEALTH_POLL_SECONDS=0
state_file="$tmpdir/state"

install_mock() {
  MOCK_SCENARIO="$1"
  printf '0\n' >"$state_file"
  run_root() {
    case "$*" in
      'docker compose ps -aq') printf 'container-1\n' ;;
      *"--format {{.Name}}"*) printf '/test-container\n' ;;
      *"--format {{.State.Status}}"*)
        if [[ "$MOCK_SCENARIO" == stopped ]]; then printf 'exited\n'; else printf 'running\n'; fi
        ;;
      *"--format {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"*)
        local count
        count="$(<"$state_file")"
        count=$((count + 1))
        printf '%s\n' "$count" >"$state_file"
        case "$MOCK_SCENARIO" in
          transition) if (( count == 1 )); then printf 'starting\n'; else printf 'healthy\n'; fi ;;
          timeout) printf 'starting\n' ;;
          unhealthy) printf 'unhealthy\n' ;;
          stopped) printf 'healthy\n' ;;
        esac
        ;;
      *) printf 'unexpected mock command: %s\n' "$*" >&2; return 1 ;;
    esac
  }
}

install_mock transition
HEALTH_TIMEOUT_SECONDS=5
transition_output="$(wait_stack_health "$tmpdir/stack" test)"
grep -Fq 'health=starting, nouvelle vérification' <<<"$transition_output"
grep -Fq 'tous les conteneurs sont prêts' <<<"$transition_output"

install_mock timeout
HEALTH_TIMEOUT_SECONDS=0
if timeout_output="$(wait_stack_health "$tmpdir/stack" test 2>&1)"; then
  printf 'timeout scenario unexpectedly succeeded\n' >&2
  exit 1
fi
grep -Fq 'timeout après 0s' <<<"$timeout_output"

install_mock unhealthy
HEALTH_TIMEOUT_SECONDS=5
if unhealthy_output="$(wait_stack_health "$tmpdir/stack" test 2>&1)"; then
  printf 'unhealthy scenario unexpectedly succeeded\n' >&2
  exit 1
fi
grep -Fq 'healthcheck unhealthy' <<<"$unhealthy_output"

install_mock stopped
if stopped_output="$(wait_stack_health "$tmpdir/stack" test 2>&1)"; then
  printf 'stopped scenario unexpectedly succeeded\n' >&2
  exit 1
fi
grep -Fq 'conteneur non démarré' <<<"$stopped_output"

printf 'container patching health tests passed\n'
