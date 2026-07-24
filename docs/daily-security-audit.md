# Deterministic daily security audit

The daily security report uses [`scripts/daily-security-audit.py`](../scripts/daily-security-audit.py) as a versioned, read-only data collector. Hermes interprets the bounded JSON and writes the concise WhatsApp report; it does not construct the underlying system probes dynamically.

## Security contract

The collector:

- invokes commands without a shell;
- uses `sudo -n` only for bounded read-only probes;
- applies an explicit timeout to every subprocess and HTTP request;
- limits captured command output to 1 MB per stream;
- emits one JSON document even when one subsystem is unavailable;
- never emits UniFi API keys, environment variables, raw SSH logs, Restic lock IDs, backup paths, or Restic journal lines;
- performs no package update, restart, firewall mutation, ban, device adoption, backup, restore, prune, or container deployment.

The root-only `/usr/local/sbin/infraforge-backup-audit.sh` is executed directly through `sudo -n`. That script is the repository-managed, read-only Restic audit already used by `ansible/playbooks/audit_vps.yml`; the collector retains only its health summary.

## Collected sections

Schema version 1 contains:

- disk, inode, `/var/log`, and journald usage;
- pending package count, reboot-required state, and failed units;
- required service state, including the Hermes user gateway;
- public listening TCP/UDP ports and UFW default posture;
- aggregate SSH authentication and fail2ban counts for 24 hours;
- bounded reachability checks for the VPN peer and known UniFi gateways;
- sanitized Docker container state;
- HTTP health for Caddy/Authentik, NetBox, Authentik, Semaphore, and trusted-TLS OpenBao health;
- adopted/offline UniFi devices, aggregate client counts, and classified rogue-AP observations;
- sanitized Restic service, snapshot age, lock count, application-completeness, and next-run state.

UDP ports 68 and 546 are excluded from public-service findings because they are DHCP client listeners, not server exposure.

## Rogue-AP semantics

An entry marked `is_rogue` is classified by normalized `last_seen`/`report_time`:

- less than 15 minutes: `active`;
- 15 minutes to 24 hours: `recent` but not active;
- older than 24 hours or without a usable timestamp: `historical`.

The collector preserves SSID, BSSID, signal, channel, UniFi/vendor flags, neighbor status, and whether the SSID is known. The reporting agent must not describe a marked or recently seen radio as a verified intrusion without independent evidence.

## Deployment

The repository file is the source of truth. Hermes executes the deployed copy:

```text
/home/debian/.hermes/scripts/daily_security_audit.py
```

The daily cron job attaches `daily_security_audit.py` through its `script` field with `no_agent=false`. Script stdout is injected as context; Hermes then interprets the JSON and delivers the report.

After changing the collector:

1. run the unit and repository suites;
2. execute one real read-only collection and validate the JSON;
3. install the tested file with mode `0755`;
4. compare repository and deployed checksums;
5. run the attached cron once and inspect its delivered summary;
6. keep the next scheduled execution at 08:00 Europe/Paris time.

## Validation

```bash
python3 scripts/tests/daily-security-audit.test.py
make check
make scan
```

The unit suite covers public-listener filtering, UFW parsing, UniFi timestamps in seconds and milliseconds, the 15-minute rogue threshold, Restic minimization, and the complete schema with mocked probes.
