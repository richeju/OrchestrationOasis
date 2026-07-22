#!/usr/bin/env bash
set -euo pipefail

PATH="${PATCHING_PATH:-/usr/sbin:/usr/bin:/sbin:/bin}"
export DEBIAN_FRONTEND=noninteractive

LOG_DIR="${LOG_DIR:-/home/debian/.hermes/cron/output}"
AUTHENTIK_DIR="${AUTHENTIK_DIR:-/home/debian/authentik}"
NETBOX_DIR="${NETBOX_DIR:-/home/debian/netbox}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-300}"
HEALTH_POLL_SECONDS="${HEALTH_POLL_SECONDS:-10}"
dry_run="${DRY_RUN:-0}"

say() { printf '%s\n' "$*"; }
section() { printf '\n=== %s ===\n' "$*"; }

have_sudo=yes
if ! sudo -n true >/dev/null 2>&1; then
  have_sudo=no
fi

run_root() {
  if [[ "$have_sudo" != yes ]]; then
    say "ERREUR: sudo non interactif indisponible"
    return 1
  fi
  if [[ "$dry_run" == "1" ]]; then
    say "[DRY-RUN] sudo $*"
    return 0
  fi
  sudo -n "$@"
}

compose_patch() {
  local dir="$1"
  local name="$2"
  section "STACK $name"
  if [[ ! -d "$dir" ]]; then
    say "$name: dossier absent ($dir)"
    return 1
  fi
  pushd "$dir" >/dev/null
  say "$name: pull des images"
  run_root docker compose pull
  say "$name: application des mises à jour"
  run_root docker compose up -d
  say "$name: état initial"
  run_root docker compose ps
  popd >/dev/null
}

container_state() {
  local id="$1"
  local cname status health
  cname="$(run_root docker inspect --format '{{.Name}}' "$id" | sed 's#^/##')"
  status="$(run_root docker inspect --format '{{.State.Status}}' "$id")"
  health="$(run_root docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id")"
  printf '%s\t%s\t%s\n' "$cname" "$status" "$health"
}

wait_stack_health() {
  local dir="$1"
  local name="$2"
  local deadline=$(( $(date +%s) + HEALTH_TIMEOUT_SECONDS ))
  local ids

  pushd "$dir" >/dev/null
  ids="$(run_root docker compose ps -aq || true)"
  if [[ -z "$ids" ]]; then
    say "$name: aucun conteneur détecté"
    popd >/dev/null
    return 1
  fi

  while true; do
    local pending=0
    local failed=0
    local id cname status health
    for id in $ids; do
      IFS=$'\t' read -r cname status health < <(container_state "$id")
      say "$name/$cname: status=$status health=$health"
      if [[ "$status" != running ]]; then
        say "$name/$cname: échec, conteneur non démarré"
        failed=1
      elif [[ "$health" == unhealthy ]]; then
        say "$name/$cname: échec, healthcheck unhealthy"
        failed=1
      elif [[ "$health" == starting ]]; then
        pending=1
      elif [[ "$health" != healthy && "$health" != none ]]; then
        say "$name/$cname: échec, état de santé inconnu: $health"
        failed=1
      fi
    done

    if (( failed != 0 )); then
      popd >/dev/null
      return 1
    fi
    if (( pending == 0 )); then
      say "$name: tous les conteneurs sont prêts"
      popd >/dev/null
      return 0
    fi
    if (( $(date +%s) >= deadline )); then
      say "$name: timeout après ${HEALTH_TIMEOUT_SECONDS}s en attente de healthy"
      popd >/dev/null
      return 1
    fi
    say "$name: health=starting, nouvelle vérification dans ${HEALTH_POLL_SECONDS}s"
    sleep "$HEALTH_POLL_SECONDS"
  done
}

main() {
  mkdir -p "$LOG_DIR"
  local run_ts log_file
  run_ts="$(date '+%F_%H%M%S')"
  log_file="$LOG_DIR/sunday_container_patching_${run_ts}.log"
  exec > >(tee -a "$log_file") 2>&1

  section "MÉTA"
  say "Date: $(date -Is)"
  say "Hôte: $(hostname)"
  say "Log: $log_file"

  if [[ "$have_sudo" != yes ]]; then
    say "❌ Procédure KO: sudo non interactif absent"
    exit 1
  fi

  section "AVANT"
  say "Kernel: $(uname -r)"
  say "Disque /: $(df -h / | awk 'NR==2{print $5" utilisé, "$4" libres"}')"
  run_root systemctl is-active docker >/dev/null
  say "Docker: actif"

  section "PATCH HOST"
  local host_upgradable_before host_upgradable_after
  host_upgradable_before="$(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')"
  say "Paquets upgradables avant: ${host_upgradable_before}"
  run_root apt-get update
  run_root apt-get -y upgrade
  if [[ "$dry_run" == "1" ]]; then
    host_upgradable_after="$host_upgradable_before"
  else
    host_upgradable_after="$(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')"
  fi
  say "Paquets upgradables après: ${host_upgradable_after}"

  compose_patch "$AUTHENTIK_DIR" "authentik"
  compose_patch "$NETBOX_DIR" "netbox"

  section "VÉRIFICATIONS"
  local errors=0
  if [[ "$dry_run" == "1" ]]; then
    say "Mode simulation: vérifications santé finales non exécutées"
  else
    if ! wait_stack_health "$AUTHENTIK_DIR" "authentik"; then
      say "authentik: vérification santé KO"
      errors=1
    fi
    if ! wait_stack_health "$NETBOX_DIR" "netbox"; then
      say "netbox: vérification santé KO"
      errors=1
    fi
  fi

  local reboot_required=no
  if [[ -f /var/run/reboot-required ]]; then
    reboot_required=yes
  fi
  say "Reboot requis: $reboot_required"

  section "RÉSUMÉ"
  if [[ "$errors" -eq 0 ]]; then
    say "✅ Patching hebdo terminé"
  else
    say "⚠️ Patching hebdo terminé avec anomalies"
  fi
  say "Host: upgradable avant=${host_upgradable_before}, après=${host_upgradable_after}, reboot=${reboot_required}"
  say "Stacks traitées: authentik, netbox"
  say "Semaphore: service host séparé, non redéployé par cette procédure"
  say "Log détaillé: $log_file"

  if [[ "$errors" -ne 0 ]]; then
    exit 1
  fi
}

if [[ "${PATCHING_LIB_ONLY:-0}" != 1 ]]; then
  main "$@"
fi
