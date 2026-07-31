#!/usr/bin/env python3
"""Collect a bounded, read-only VPS and UniFi security snapshot as JSON."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import signal
import shutil
import ssl
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

SCHEMA_VERSION = 1
DEFAULT_UNIFI_HOST = "https://10.57.50.1"
DEFAULT_UNIFI_SITE = "default"
DEFAULT_VPN_TARGETS = (
    "10.78.0.2",
    "10.57.50.1",
    "10.57.99.1",
    "10.57.100.1",
    "10.57.101.1",
    "10.57.110.1",
)
KNOWN_SSIDS = {"Gods", "Enligne Wireless"}
NON_SERVICE_WILDCARD_LISTENERS = {("udp", "68"), ("udp", "546")}
MAX_OUTPUT_BYTES = 1_000_000
DEFAULT_UNIFI_CERT_SHA256 = (
    "8fb4fdfc9b329247052c80077adb51fc3754fe09c389af8aeca75d648b32cae4"
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    error: str | None = None


def run_command(
    argv: Sequence[str], *, timeout: int = 20, sudo: bool = False
) -> CommandResult:
    command = ["sudo", "-n", *argv] if sudo else list(argv)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return CommandResult(127, "", "", type(exc).__name__)

    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    stdout_state = {"truncated": False}
    stderr_state = {"truncated": False}

    def drain(stream: Any, buffer: bytearray, state: dict[str, bool]) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            remaining = MAX_OUTPUT_BYTES - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
            if len(chunk) > max(remaining, 0):
                state["truncated"] = True

    threads = [
        threading.Thread(
            target=drain,
            args=(process.stdout, stdout_buffer, stdout_state),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(process.stderr, stderr_buffer, stderr_state),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    error: str | None = None
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        error = "timeout"
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        returncode = process.wait()
    for thread in threads:
        thread.join(timeout=5)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    if error is None and (stdout_state["truncated"] or stderr_state["truncated"]):
        error = "output_truncated"

    stdout = bytes(stdout_buffer).decode("utf-8", errors="replace")
    stderr = bytes(stderr_buffer).decode("utf-8", errors="replace")
    return CommandResult(
        124 if error == "timeout" else returncode,
        stdout,
        stderr,
        error,
    )


def error_record(probe: str, result: CommandResult | Exception | str) -> dict[str, str]:
    if isinstance(result, CommandResult):
        detail = result.error or f"exit_{result.returncode}"
    elif isinstance(result, Exception):
        detail = type(result).__name__
    else:
        detail = result
    return {"probe": probe, "error": detail[:120]}


def epoch_seconds(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return value / 1000 if value > 1_000_000_000_000 else float(value)


def disk_snapshot(path: str) -> dict[str, int]:
    usage = shutil.disk_usage(path)
    stat = os.statvfs(path)
    inode_total = stat.f_files
    inode_used = inode_total - stat.f_ffree
    return {
        "used_percent": round(usage.used * 100 / usage.total),
        "free_bytes": usage.free,
        "inode_used_percent": round(inode_used * 100 / inode_total) if inode_total else 0,
    }


def parse_size_bytes(text: str) -> int | None:
    match = re.search(
        r"([0-9]+(?:[.,][0-9]+)?)\s*([KMGT]?)(?:i?B)?(?=\s|[.]|$)",
        text,
        re.I,
    )
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    power = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4}[match.group(2).upper()]
    return round(value * (1024**power))


def normalize_listener_host(local_address: str) -> str:
    if local_address.startswith("[") and "]:" in local_address:
        return local_address[1 : local_address.rfind("]:")]
    return local_address.rsplit(":", 1)[0]


def parse_public_listeners(text: str) -> list[dict[str, str]]:
    listeners: set[tuple[str, str]] = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        protocol = fields[0].lower()
        local = fields[4]
        host = normalize_listener_host(local)
        port = local.rsplit(":", 1)[-1]
        public = host in {"*", "0.0.0.0", "::"}
        if not public:
            try:
                address = ipaddress.ip_address(host.split("%", 1)[0])
                public = address.is_global
            except ValueError:
                public = False
        if public:
            listener = (protocol, port)
            if listener not in NON_SERVICE_WILDCARD_LISTENERS:
                listeners.add(listener)
    return [
        {"protocol": protocol, "port": port}
        for protocol, port in sorted(listeners)
    ]


def count_apt_updates(text: str) -> int:
    return sum(1 for line in text.splitlines() if "/" in line and not line.startswith("Listing"))


def parse_failed_units(text: str) -> list[str]:
    return [line.split()[0] for line in text.splitlines() if line.split()]


def parse_ssh_activity(text: str) -> dict[str, int]:
    failures = 0
    successes = 0
    failed_ips: set[str] = set()
    for line in text.splitlines():
        lowered = line.lower()
        if any(token in lowered for token in ("failed password", "invalid user", "authentication failure")):
            failures += 1
            match = re.search(r"\bfrom\s+(\S+)", line, re.I)
            if match:
                candidate = match.group(1).strip("[]").split("%", 1)[0]
                try:
                    address = ipaddress.ip_address(candidate)
                except ValueError:
                    pass
                else:
                    failed_ips.add(str(address))
        if "accepted publickey" in lowered or "accepted password" in lowered:
            successes += 1
    return {
        "failed_attempts_24h": failures,
        "unique_failed_ips_24h": len(failed_ips),
        "successful_logins_24h": successes,
    }


def parse_fail2ban(text: str) -> dict[str, int | None]:
    current = re.search(r"Currently banned:\s*(\d+)", text)
    total = re.search(r"Total banned:\s*(\d+)", text)
    return {
        "currently_banned": int(current.group(1)) if current else None,
        "total_banned": int(total.group(1)) if total else None,
    }


def parse_ufw(text: str) -> dict[str, Any]:
    status = re.search(r"^Status:\s*(\w+)", text, re.M | re.I)
    default = re.search(r"^Default:\s*([^\n]+)", text, re.M | re.I)
    default_text = default.group(1).strip().lower() if default else ""
    return {
        "active": bool(status and status.group(1).lower() == "active"),
        "default_incoming_deny": "deny (incoming)" in default_text,
        "default_outgoing_allow": "allow (outgoing)" in default_text,
    }


def parse_container_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append(
            {
                "name": str(item.get("Names", "")),
                "state": str(item.get("State", "")),
                "status": str(item.get("Status", "")),
            }
        )
    return rows


def classify_rogues(
    rows: list[dict[str, Any]], *, now: float, known_ssids: set[str] | None = None
) -> dict[str, list[dict[str, Any]]]:
    known_ssids = known_ssids or KNOWN_SSIDS
    result: dict[str, list[dict[str, Any]]] = {
        "active": [],
        "recent": [],
        "historical": [],
    }
    for row in rows:
        if not row.get("is_rogue"):
            continue
        seen = epoch_seconds(row.get("last_seen") or row.get("report_time"))
        age_minutes = round((now - seen) / 60, 1) if seen else None
        item = {
            "ssid": row.get("essid") or row.get("ssid"),
            "bssid": row.get("bssid") or row.get("mac"),
            "age_minutes": age_minutes,
            "signal_dbm": row.get("signal"),
            "channel": row.get("channel"),
            "is_unifi": bool(row.get("is_unifi") or row.get("is_ubnt")),
            "is_neighbor": bool(row.get("is_neighbor")),
            "known_ssid": (row.get("essid") or row.get("ssid")) in known_ssids,
        }
        if age_minutes is not None and 0 <= age_minutes < 15:
            result["active"].append(item)
        elif age_minutes is not None and 0 <= age_minutes < 1440:
            result["recent"].append(item)
        else:
            result["historical"].append(item)
    return result


def summarize_unifi(
    devices: list[dict[str, Any]],
    clients: list[dict[str, Any]],
    rogues: list[dict[str, Any]],
    *,
    now: float,
) -> dict[str, Any]:
    adopted = [row for row in devices if row.get("adopted")]
    known_ssids = set(KNOWN_SSIDS)
    for device in adopted:
        for vap in device.get("vap_table") or []:
            ssid = vap.get("essid") or vap.get("ssid")
            if ssid:
                known_ssids.add(str(ssid))
    pending = [
        {
            "name": row.get("name"),
            "model": row.get("model"),
            "mac": row.get("mac"),
            "ip": row.get("ip"),
            "state": row.get("state"),
        }
        for row in devices
        if not row.get("adopted") or row.get("state") not in (1,)
    ]
    new_clients = 0
    for client in clients:
        first_seen = epoch_seconds(client.get("first_seen"))
        if first_seen and 0 <= now - first_seen < 86400:
            new_clients += 1
    return {
        "adopted_online": sum(1 for row in adopted if row.get("state") == 1),
        "adopted_total": len(adopted),
        "pending_or_offline": pending,
        "active_clients": len(clients),
        "unnamed_clients": sum(
            1 for row in clients if not str(row.get("name") or row.get("hostname") or "").strip()
        ),
        "new_clients_24h": new_clients,
        "rogue_detections": classify_rogues(
            rogues, now=now, known_ssids=known_ssids
        ),
    }


def sanitize_restic(data: dict[str, Any]) -> dict[str, Any]:
    latest = data.get("latest_snapshot") or {}
    service = data.get("service") or {}
    timer = data.get("timer") or {}
    return {
        "status": data.get("status"),
        "reasons": data.get("reasons") or [],
        "service_result": service.get("Result"),
        "service_exit_status": service.get("ExecMainStatus"),
        "snapshot_count": data.get("snapshot_count"),
        "latest_snapshot_age_hours": latest.get("age_hours"),
        "locks_count": len(data.get("locks") or []),
        "application_backup_complete": data.get("application_backup_complete"),
        "next_run": timer.get("NextElapseUSecRealtime"),
    }


def normalize_sha256_fingerprint(value: str) -> str:
    normalized = re.sub(r"[^0-9a-f]", "", value.lower())
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("invalid SHA-256 certificate fingerprint")
    return normalized


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that verifies the peer before sending HTTP bytes."""

    def __init__(self, host: str, port: int, fingerprint: str, timeout: int) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__(host, port=port, timeout=timeout, context=context)
        self.expected_fingerprint = normalize_sha256_fingerprint(fingerprint)

    def connect(self) -> None:
        super().connect()
        if self.sock is None:
            raise ssl.SSLError("TLS socket unavailable")
        certificate = self.sock.getpeercert(binary_form=True)
        if not certificate:
            self.close()
            raise ssl.SSLError("UniFi peer certificate unavailable")
        actual = hashlib.sha256(certificate).hexdigest()
        if not hmac.compare_digest(actual, self.expected_fingerprint):
            self.close()
            raise ssl.SSLError("UniFi certificate fingerprint mismatch")


def unifi_get(path: str) -> list[dict[str, Any]]:
    api_key = os.environ.get("UNIFI_API_KEY")
    if not api_key:
        raise RuntimeError("UNIFI_API_KEY is unavailable")
    base = urllib.parse.urlsplit(os.environ.get("UNIFI_HOST", DEFAULT_UNIFI_HOST))
    if (
        base.scheme != "https"
        or not base.hostname
        or base.username
        or base.password
        or base.path not in ("", "/")
        or base.query
        or base.fragment
    ):
        raise RuntimeError("UNIFI_HOST must be a plain HTTPS origin")
    fingerprint = os.environ.get("UNIFI_CERT_SHA256", DEFAULT_UNIFI_CERT_SHA256)
    connection = PinnedHTTPSConnection(
        base.hostname,
        base.port or 443,
        fingerprint,
        timeout=15,
    )
    request_path = f"{base.path.rstrip('/')}{path}"
    try:
        connection.request(
            "GET",
            request_path,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"UniFi API returned HTTP {response.status}")
        raw = response.read(MAX_OUTPUT_BYTES + 1)
        if len(raw) > MAX_OUTPUT_BYTES:
            raise RuntimeError("UniFi API response exceeds output limit")
        body = json.loads(raw)
    finally:
        connection.close()
    data = body.get("data", [])
    if not isinstance(data, list):
        raise ValueError("UniFi API data is not a list")
    return data


def probe_http(url: str, *, host_header: str | None = None) -> dict[str, Any]:
    headers = {"Host": host_header} if host_header else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"ok": 200 <= response.status < 400, "status": response.status}
    except urllib.error.HTTPError as exc:
        return {"ok": 200 <= exc.code < 400, "status": exc.code}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def probe_openbao() -> dict[str, Any]:
    url = "https://10.78.0.1:8200/v1/sys/health"
    ca_path = "/home/debian/openbao/tls/ca.crt"
    try:
        context = ssl.create_default_context(cafile=ca_path)
        with urllib.request.urlopen(url, context=context, timeout=10) as response:
            status = response.status
            body = json.load(response)
        initialized = bool(body.get("initialized"))
        sealed = bool(body.get("sealed"))
        return {
            "ok": initialized and not sealed,
            "status": status,
            "initialized": initialized,
            "sealed": sealed,
            "standby": bool(body.get("standby")),
        }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code}
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def collect(
    *,
    runner: Callable[..., CommandResult] = run_command,
    now: dt.datetime | None = None,
    unifi_reader: Callable[[str], list[dict[str, Any]]] = unifi_get,
) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc).astimezone()
    errors: list[dict[str, str]] = []
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "read_only": True,
        "errors": errors,
    }

    storage: dict[str, Any] = {"root": disk_snapshot("/")}
    report["storage"] = storage
    du = runner(["du", "-sb", "/var/log"], timeout=20, sudo=True)
    storage["var_log_bytes"] = None
    if du.returncode == 0:
        try:
            storage["var_log_bytes"] = int(du.stdout.split()[0])
        except (IndexError, ValueError):
            errors.append(error_record("var_log_size", "unparseable_output"))
    else:
        errors.append(error_record("var_log_size", du))
    journal_size = runner(["journalctl", "--disk-usage", "--no-pager"], timeout=15, sudo=True)
    storage["journald_bytes"] = parse_size_bytes(journal_size.stdout)
    if journal_size.returncode != 0:
        errors.append(error_record("journald_size", journal_size))

    apt = runner(["apt", "list", "--upgradable"], timeout=25)
    failed_units = runner(["systemctl", "--failed", "--no-legend", "--plain"], timeout=15)
    report["host"] = {
        "pending_updates": count_apt_updates(apt.stdout) if apt.returncode == 0 else None,
        "reboot_required": Path("/var/run/reboot-required").exists(),
        "failed_units": parse_failed_units(failed_units.stdout) if failed_units.returncode == 0 else [],
    }
    if apt.returncode != 0:
        errors.append(error_record("apt_updates", apt))
    if failed_units.returncode != 0:
        errors.append(error_record("failed_units", failed_units))

    services: dict[str, str] = {}
    for unit in ("ssh.service", "ufw.service", "fail2ban.service", "openvpn-hermes-ovh.service", "docker.service", "caddy.service"):
        result = runner(["systemctl", "is-active", unit], timeout=10)
        services[unit] = result.stdout.strip() or "unknown"
    hermes = runner(["systemctl", "--user", "is-active", "hermes-gateway.service"], timeout=10)
    services["hermes-gateway.service"] = hermes.stdout.strip() or "unknown"
    report["services"] = services

    ss_result = runner(["ss", "-H", "-lntu"], timeout=15, sudo=True)
    report["public_listeners"] = parse_public_listeners(ss_result.stdout)
    if ss_result.returncode != 0:
        errors.append(error_record("public_listeners", ss_result))

    ufw = runner(["ufw", "status", "verbose"], timeout=15, sudo=True)
    report["firewall"] = parse_ufw(ufw.stdout)
    if ufw.returncode != 0:
        errors.append(error_record("ufw", ufw))

    ssh_journal = runner(
        ["journalctl", "-u", "ssh", "--since", "24 hours ago", "--no-pager", "-o", "cat"],
        timeout=25,
        sudo=True,
    )
    ssh_summary: dict[str, Any] = parse_ssh_activity(ssh_journal.stdout)
    report["ssh"] = ssh_summary
    if ssh_journal.returncode != 0:
        errors.append(error_record("ssh_activity", ssh_journal))
    f2b = runner(["fail2ban-client", "status", "sshd"], timeout=15, sudo=True)
    ssh_summary["fail2ban"] = parse_fail2ban(f2b.stdout)
    if f2b.returncode != 0:
        errors.append(error_record("fail2ban", f2b))

    vpn_targets: dict[str, bool] = {}
    for target in DEFAULT_VPN_TARGETS:
        ping = runner(["ping", "-n", "-c", "1", "-W", "2", target], timeout=5)
        vpn_targets[target] = ping.returncode == 0
    report["vpn"] = {"targets": vpn_targets}

    containers = runner(["docker", "ps", "--format", "{{json .}}"], timeout=20, sudo=True)
    report["containers"] = parse_container_rows(containers.stdout)
    if containers.returncode != 0:
        errors.append(error_record("docker_containers", containers))

    report["http_services"] = {
        "caddy_authentik": probe_http("http://10.78.0.1/", host_header="auth.jrnet.fr"),
        "netbox": probe_http("http://10.78.0.1:8000/login/"),
        "authentik": probe_http("http://10.78.0.1:9000/"),
        "semaphore": probe_http("http://10.78.0.1:3001/"),
        "openbao": probe_openbao(),
    }

    site = os.environ.get("UNIFI_SITE", DEFAULT_UNIFI_SITE)
    try:
        devices = unifi_reader(f"/proxy/network/api/s/{site}/stat/device")
        clients = unifi_reader(f"/proxy/network/api/s/{site}/stat/sta")
        rogues = unifi_reader(f"/proxy/network/api/s/{site}/stat/rogueap")
        report["unifi"] = summarize_unifi(
            devices, clients, rogues, now=now.timestamp()
        )
    except Exception as exc:  # The report must survive one unavailable subsystem.
        report["unifi"] = {"available": False}
        errors.append(error_record("unifi", exc))

    restic = runner(["/usr/local/sbin/infraforge-backup-audit.sh"], timeout=90, sudo=True)
    if restic.returncode == 0:
        try:
            report["backup"] = sanitize_restic(json.loads(restic.stdout))
        except json.JSONDecodeError:
            report["backup"] = {"status": "unknown"}
            errors.append(error_record("restic_audit", "invalid_json"))
    else:
        report["backup"] = {"status": "unknown"}
        errors.append(error_record("restic_audit", restic))

    return report


def main() -> int:
    report = collect()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
