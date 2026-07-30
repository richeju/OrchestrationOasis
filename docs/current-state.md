# Current infrastructure state

This page is the canonical boundary between observed production state and the
automation currently owned by this repository. It contains no credentials.

Last verified: 2026-07-22 from the Infraforge VPS.

## Status vocabulary

- **Managed**: the repository can converge and validate the deployed instance.
- **Migrated**: a repository role performed a reviewed migration and owns future
  convergence.
- **Observed**: the audit checks the service, but this repository must not
  redeploy it.
- **Partial**: automation converges some runtime configuration, but one or more
  operational ownership criteria below remain incomplete.
- **Planned**: automation exists or is proposed but is not enabled in production.

## Service matrix

| Service | Production implementation | Exposure | Repository status |
| --- | --- | --- | --- |
| Docker | Native systemd service | Host local | Managed baseline |
| OpenVPN site-to-site | Native `openvpn-hermes-ovh.service`, interface `tun-hermes` | Private routes between VPS and home LANs | Observed only |
| Caddy | Native systemd service; Authentik reverse proxy | VPN HTTP `10.78.0.1:80` | Observed only |
| Semaphore | Docker Compose in `/home/debian/semaphore` | VPN `10.78.0.1:3001` | Migrated and managed |
| OpenBao | Docker Compose in `/home/debian/openbao` | VPN TLS `10.78.0.1:8200` | Partial; automated Raft snapshots are managed, isolated full restore remains |
| Restic/rclone | Native root-only scripts, application-consistent export hook and systemd timers | No listening port | Managed backup pipeline; latest read-only audit healthy, full disposable offsite restore automation remains backlog |
| Hermes Agent | Per-user Python installation and user systemd messaging gateway | Outbound WhatsApp gateway | Partial; live role and application-consistent backup/transaction safeguards verified, second-convergence proof remains pending |
| NetBox | Official netbox-docker stack in `/home/debian/netbox`, including worker, PostgreSQL and Valkey | VPN `10.78.0.1:8000` | Observed only |
| Authentik | Docker Compose in `/home/debian/authentik` | VPN `10.78.0.1:9000` | Observed only |
| Prometheus | Not detected | None | Planned |
| BIND, Dashy, ZeroTier container | Not part of the verified VPS runtime | None verified | Planned |
| UFW and YubiKey SSH MFA | Host-sensitive controls | Host | Opt-in only |

## NetBox boundary

The `roles/netbox` role is a legacy compact bootstrap stack. It is not compatible
with the official production topology and is disabled unless
`netbox_compact_stack_confirmed=true` is supplied explicitly. Do not use that
role to update the current production NetBox. A future migration must first
model the official stack, backup PostgreSQL and media, and exercise restore and
rollback tests.

## Read-only VPS audit

`playbooks/audit_vps.yml` targets only the `infraforge_vps` inventory group. Its
non-secret topology is versioned in
`playbooks/group_vars/infraforge_vps.yml`. The audit verifies required systemd
units, failed units, private HTTP endpoints, OpenBao TLS health, and Restic
repository health without changing the host.

Semaphore must use the inventory shape documented in
`ansible/inventories/semaphore-vps.example.yml`; the host remains a member of
both `infraforge_vps` and the broader `linux` group.

The daily WhatsApp security report uses the deterministic, versioned collector
documented in [`daily-security-audit.md`](daily-security-audit.md). Its
2026-07-22 production run completed without collection errors and verified a
restrictive UFW posture, only SSH and OpenVPN on public listeners, healthy
private service probes, initialized/unsealed OpenBao, and a healthy Restic
snapshot with no lock and a complete application export. The host had no
pending package updates but did report that a reboot was required; no reboot
was performed by the audit.

Weekly maintenance now separates mutation and recovery validation: patching runs
Sunday at 22:30, the host is rebooted Monday at 03:30 only when Debian's
`reboot-required` marker exists, and a silent-unless-needed verification runs
at 03:45. The implementation and safeguards are documented in
[`weekly-conditional-reboot.md`](weekly-conditional-reboot.md).

Daily repository maintenance is launched at 10:00 after the 08:00 security
audit. Logs, container health, CI messages, issues, and documented debt are
ranked as evidence for at most one low-risk bugfix or improvement. Work uses a
`daily/*` branch and mandatory PR/check/scan gates; sensitive infrastructure
changes remain human-approved. The bounded worker and reporting pipeline are
documented in
[`daily-repository-maintenance.md`](daily-repository-maintenance.md).

## Change rule

A service moves from **Observed** or **Planned** to **Managed** only when its role
has all of the following:

1. an explicit inventory group and documented dependencies;
2. safe defaults and pre-mutation assertions;
3. rendered configuration tests;
4. a runtime health probe;
5. an idempotence test or a recorded second-convergence result;
6. a service-aware backup and tested rollback path for persistent data.
