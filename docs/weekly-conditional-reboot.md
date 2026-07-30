# Weekly conditional reboot

The VPS uses a two-stage Hermes cron workflow after the Sunday patching window. It does **not** reboot every week unconditionally.

## Schedule

All times use the scheduler timezone (`Europe/Paris`):

- Sunday `22:30`: host and container patching;
- Monday `03:30`: conditional reboot preparation;
- Monday `03:45`: post-boot verification.

If `/var/run/reboot-required` is absent at 03:30, the preparation script prints nothing, schedules nothing, and Hermes sends no notification.

## Source of truth

The shared implementation is [`scripts/weekly-conditional-reboot.py`](../scripts/weekly-conditional-reboot.py). It is installed under two names so execution mode is explicit:

```text
/home/debian/.hermes/scripts/weekly_reboot_prepare.py
/home/debian/.hermes/scripts/weekly_reboot_verify.py
```

Both cron jobs use `no_agent=true`; their exact bounded stdout is delivered without an LLM or additional tool calls.

## Preparation transaction

When Debian requests a reboot, the preparation mode:

1. refuses to schedule a duplicate while a prior state file exists;
2. creates a root transient systemd timer through `sudo -n systemd-run`;
3. schedules `/usr/bin/systemctl reboot` two minutes later;
4. verifies that the transient timer is active;
5. writes the current boot ID, request timestamp, and transient unit name atomically to a mode `0600` state file;
6. emits the pre-reboot notification.

If timer activation cannot be verified, it is stopped and no state is persisted. The two-minute delay lets Hermes finish delivering the preparation notification before the gateway stops.

State path:

```text
/home/debian/.hermes/state/weekly-reboot.json
```

## Post-boot verification

At 03:45, verification is silent when no state file exists. Otherwise it confirms:

- the kernel boot ID changed;
- `/var/run/reboot-required` disappeared;
- SSH, UFW, fail2ban, OpenVPN, Docker, Caddy, and the Hermes gateway are active;
- systemd has no failed units;
- every expected Authentik, NetBox, OpenBao, and Semaphore container is running and not `starting` or `unhealthy`;
- the UniFi controller is reachable through the VPN;
- Caddy/Authentik, NetBox, Authentik, Semaphore, and trusted-TLS OpenBao probes are healthy.

The state file is removed after a definitive success or failure report. A boot-ID mismatch is required before reporting that a reboot succeeded.

## Safety properties

- No reboot occurs without Debian's `reboot-required` marker.
- Preparation is idempotent while state is pending.
- No shell is used for command execution.
- Timer activation is verified before state is committed.
- A failed preparation never claims that a reboot was scheduled.
- Verification never hides a partial recovery behind a success message.
- No credential, environment variable, raw journal, or command stderr is delivered.

## Validation

```bash
python3 scripts/tests/weekly-conditional-reboot.test.py
make check
make scan
```

The unit suite covers the silent no-marker path, verified scheduling and secure state persistence, scheduling failure, unchanged boot detection, and complete post-boot health validation with mocked commands and endpoints. Do not manually execute the deployed preparation mode while `reboot-required` exists merely to test it: that would schedule a real reboot.
