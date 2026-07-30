#!/usr/bin/env python3
"""Schedule and verify a weekly reboot only when Debian requests one."""

from __future__ import annotations

import datetime as dt
import json
import os
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

REBOOT_MARKER = Path("/var/run/reboot-required")
BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
STATE_PATH = Path("/home/debian/.hermes/state/weekly-reboot.json")
REBOOT_DELAY = "2m"
SYSTEM_SERVICES = (
    "ssh.service",
    "ufw.service",
    "fail2ban.service",
    "openvpn-hermes-ovh.service",
    "docker.service",
    "caddy.service",
)
REQUIRED_CONTAINERS = {
    "authentik-postgresql-1",
    "authentik-server-1",
    "authentik-worker-1",
    "netbox-netbox-1",
    "netbox-netbox-worker-1",
    "netbox-postgres-1",
    "netbox-redis-1",
    "netbox-redis-cache-1",
    "openbao",
    "semaphore",
}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def run_command(
    argv: Sequence[str], *, timeout: int = 30, sudo: bool = False
) -> CommandResult:
    command = ["sudo", "-n", *argv] if sudo else list(argv)
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(124)
    except OSError:
        return CommandResult(127)
    return CommandResult(result.returncode, result.stdout[:200_000], result.stderr[:200_000])


def read_boot_id(path: Path = BOOT_ID_PATH) -> str:
    return path.read_text(encoding="utf-8").strip()


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def prepare(
    *,
    marker: Path = REBOOT_MARKER,
    state_path: Path = STATE_PATH,
    boot_id_path: Path = BOOT_ID_PATH,
    runner: Callable[..., CommandResult] = run_command,
    now: dt.datetime | None = None,
) -> str:
    if not marker.exists():
        return ""
    if state_path.exists():
        return "⚠️ Redémarrage non reprogrammé : un état de redémarrage précédent existe encore."

    now = now or dt.datetime.now(dt.timezone.utc).astimezone()
    unit = f"infraforge-weekly-reboot-{now:%Y%m%d-%H%M%S}"
    scheduled = runner(
        [
            "/usr/bin/systemd-run",
            f"--unit={unit}",
            f"--on-active={REBOOT_DELAY}",
            "--collect",
            "--description=Infraforge conditional weekly reboot",
            "/usr/bin/systemctl",
            "reboot",
        ],
        timeout=30,
        sudo=True,
    )
    if scheduled.returncode != 0:
        return f"⚠️ Redémarrage requis mais planification impossible (exit={scheduled.returncode})."

    timer = runner(
        ["/usr/bin/systemctl", "is-active", f"{unit}.timer"],
        timeout=15,
        sudo=True,
    )
    if timer.returncode != 0 or timer.stdout.strip() != "active":
        runner(
            ["/usr/bin/systemctl", "stop", f"{unit}.timer"],
            timeout=15,
            sudo=True,
        )
        return "⚠️ Redémarrage requis mais le timer systemd n'est pas actif."

    write_state(
        state_path,
        {
            "boot_id": read_boot_id(boot_id_path),
            "requested_at": now.isoformat(),
            "unit": unit,
        },
    )
    return (
        "🔄 Redémarrage conditionnel programmé dans 2 minutes. "
        "Une vérification automatique suivra à 03:45."
    )


def probe_http(url: str, *, host_header: str | None = None) -> bool:
    request = urllib.request.Request(
        url, headers={"Host": host_header} if host_header else {}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 400
    except (urllib.error.URLError, TimeoutError):
        return False


def probe_openbao() -> bool:
    try:
        context = ssl.create_default_context(
            cafile="/home/debian/openbao/tls/ca.crt"
        )
        with urllib.request.urlopen(
            "https://10.78.0.1:8200/v1/sys/health",
            context=context,
            timeout=10,
        ) as response:
            body = json.load(response)
        return bool(body.get("initialized")) and not bool(body.get("sealed"))
    except (OSError, ValueError, urllib.error.URLError, TimeoutError):
        return False


def endpoint_health() -> dict[str, bool]:
    return {
        "Caddy/Authentik": probe_http(
            "http://10.78.0.1/", host_header="auth.jrnet.fr"
        ),
        "NetBox": probe_http("http://10.78.0.1:8000/login/"),
        "Authentik": probe_http("http://10.78.0.1:9000/"),
        "Semaphore": probe_http("http://10.78.0.1:3001/"),
        "OpenBao": probe_openbao(),
    }


def parse_containers(text: str) -> dict[str, tuple[str, str]]:
    containers: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            containers[parts[0]] = (parts[1], parts[2])
    return containers


def verify(
    *,
    state_path: Path = STATE_PATH,
    boot_id_path: Path = BOOT_ID_PATH,
    marker: Path = REBOOT_MARKER,
    runner: Callable[..., CommandResult] = run_command,
    endpoints: Callable[[], dict[str, bool]] = endpoint_health,
) -> str:
    if not state_path.exists():
        return ""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        previous_boot = str(state["boot_id"])
    except (OSError, ValueError, KeyError, TypeError):
        state_path.unlink(missing_ok=True)
        return "⚠️ Vérification du redémarrage impossible : état local invalide."

    current_boot = read_boot_id(boot_id_path)
    issues: list[str] = []
    if current_boot == previous_boot:
        state_path.unlink(missing_ok=True)
        return "⚠️ Le redémarrage conditionnel n'a pas eu lieu : boot ID inchangé."

    if marker.exists():
        issues.append("le marqueur reboot-required est toujours présent")

    for unit in SYSTEM_SERVICES:
        result = runner(["/usr/bin/systemctl", "is-active", unit], timeout=15)
        if result.returncode != 0 or result.stdout.strip() != "active":
            issues.append(f"service {unit} non actif")

    gateway = runner(
        ["/usr/bin/systemctl", "--user", "is-active", "hermes-gateway.service"],
        timeout=15,
    )
    if gateway.returncode != 0 or gateway.stdout.strip() != "active":
        issues.append("service hermes-gateway non actif")

    failed = runner(
        ["/usr/bin/systemctl", "--failed", "--no-legend", "--plain"],
        timeout=15,
    )
    if failed.returncode != 0:
        issues.append("unités systemd en échec non vérifiables")
    elif failed.stdout.strip():
        issues.append("unités systemd en échec détectées")

    docker = runner(
        [
            "/usr/bin/docker",
            "ps",
            "--format",
            "{{.Names}}|{{.State}}|{{.Status}}",
        ],
        timeout=30,
        sudo=True,
    )
    if docker.returncode != 0:
        issues.append("conteneurs Docker non vérifiables")
    else:
        containers = parse_containers(docker.stdout)
        for name in sorted(REQUIRED_CONTAINERS):
            state_and_status = containers.get(name)
            if state_and_status is None:
                issues.append(f"conteneur {name} absent")
                continue
            container_state, status = state_and_status
            if container_state != "running" or "unhealthy" in status.lower() or "starting" in status.lower():
                issues.append(f"conteneur {name} non prêt")

    vpn = runner(["/usr/bin/ping", "-n", "-c", "1", "-W", "2", "10.57.50.1"], timeout=5)
    if vpn.returncode != 0:
        issues.append("contrôleur UniFi injoignable via VPN")

    for name, healthy in endpoints().items():
        if not healthy:
            issues.append(f"endpoint {name} indisponible")

    state_path.unlink(missing_ok=True)
    if issues:
        details = "; ".join(issues[:8])
        if len(issues) > 8:
            details += f"; +{len(issues) - 8} autre(s) anomalie(s)"
        return f"⚠️ VPS redémarré, mais vérifications incomplètes : {details}."
    return (
        "✅ VPS redémarré et entièrement opérationnel : nouveau boot confirmé, "
        "services, conteneurs, VPN et endpoints privés sains."
    )


def main() -> int:
    name = Path(sys.argv[0]).name
    if "prepare" in name:
        message = prepare()
    elif "verify" in name:
        message = verify()
    else:
        raise SystemExit(
            "invoke as weekly_reboot_prepare.py or weekly_reboot_verify.py"
        )
    if message:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
