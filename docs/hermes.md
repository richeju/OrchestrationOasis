# Hermes Agent operations

The `hermes` role manages an existing per-user Hermes Agent installation and
its messaging gateway without placing credentials in Git. Production uses the
`debian` account, `/home/debian/.hermes`, and the user unit
`hermes-gateway.service`.

## Safety contract

By default, the role:

- does **not** install or update Hermes;
- does **not** migrate `config.yaml`;
- never templates or reads credential contents;
- enforces owner/group and mode `0600` on the configured private files;
- preserves the official user systemd unit and manages only an Infraforge
  hardening drop-in, linger, enablement, and runtime state;
- runs `hermes --version`, `hermes config check`, `hermes gateway status
  --deep`, and a systemd active/running assertion after convergence.

The production private-file list includes `config.yaml`, `.env`, `auth.json`,
and the WhatsApp `creds.json`. Task output for these paths is protected with
`no_log`.

## Preview and convergence

Add the target to the `hermes` inventory group, then run:

```bash
cd ansible
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/install_hermes.yml --check --diff
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/install_hermes.yml
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/install_hermes.yml
```

The second convergence must report `changed=0`. Confirm the gateway afterwards
from an SSH session on the VPS as the configured Hermes account (`debian` in
production):

```bash
hermes config check
hermes gateway status --deep
systemctl --user status hermes-gateway.service
```

## Pinned installation or update

Installation management is opt-in. This is a code bootstrap, not a secrets
bootstrap: before the first convergence, pre-provision every path listed in
`hermes_required_private_files` as a regular file owned by the Hermes account.
Production additionally requires the existing `auth.json` and WhatsApp credentials
listed in inventory. Restore these through the documented recovery process; the
role deliberately refuses to invent or overwrite them.

Set all of the following only after reviewing the installer and the target commit:

```yaml
hermes_manage_installation: true
hermes_install_commit: "<full 40-character Git commit>"
hermes_installer_checksum: "sha256:<reviewed checksum>"
hermes_allow_checkout_replacement: true  # one reviewed adoption only
```

The installer URL itself must reference an immutable upstream commit. The role
downloads it to a root-owned, Hermes-group-readable cache (`0750` directory,
`0550` script) so the service account can execute but cannot modify it, then invokes it
with `--skip-setup`, `--non-interactive`, `--commit`, `--dir`, and
`--hermes-home`. It refuses to update a checkout with local modifications.
It refuses to replace an existing checkout unless the dedicated approval flag
is enabled. This matters because the current live checkout carries substantial
history relative to upstream. Normal production convergence leaves both
installation management and checkout replacement disabled. If the checkout is
already at the pinned commit but the configured executable is absent or unusable,
the role reruns the pinned installer so an interrupted installation can recover.
During a first-install check-mode run, Ansible reports installation changes but
skips gateway convergence and runtime probes that depend on the not-yet-created
binary. Run normal convergence next, then a second convergence for idempotence.
Gateway reload/restart handlers are inert when `hermes_manage_gateway=false`, and
the restart handler is also inert when `hermes_gateway_started=false`.

## Config migration

`hermes_migrate_config` is false by default. If explicitly enabled, migration
runs without a TTY and fails rather than waiting for an interactive answer.
The gateway is restarted only if the config checksum changed. Keep this as a
reviewed, one-time operation and return the variable to false afterwards.

## Persistent state and rollback

Hermes persistent data is backed up by the Restic application hook documented
in [restic.md](restic.md). The role owns service orchestration and private-file
metadata only; it does not replace config, OAuth state, memories, sessions,
skills, cron jobs, or the WhatsApp session.
