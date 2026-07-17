# Restic backup and restore

## Architecture

Backups use Restic directly over the root-owned rclone remote:

```text
source paths -> restic encryption/snapshots -> rclone pcloud-backup:
             -> Backups/infraforge-vps
```

Duplicati is not part of this design. There is no backup web UI and no published
backup port. The pCloud FUSE mount is not required by Restic.

## Existing Infraforge repository

The established deployment uses:

- repository: `rclone:pcloud-backup:Backups/infraforge-vps`;
- rclone config: `/root/.config/rclone/rclone.conf`;
- password file: `/root/.config/restic/infraforge-repo.pass`;
- environment file: `/root/.config/restic/infraforge.env`;
- service/timer: `infraforge-backup.service` and `infraforge-backup.timer`.

Credential files must remain owned by root with mode `0600`. Do not copy their
contents into inventory, Git, CI logs, or chat. OpenBao should hold recovery
copies or provisioning material, while the runtime identity reads only the
root-only files it needs.

## Inventory

A host opts in through the `restic` group and must define all source paths:

```yaml
restic:
  hosts:
    oasis:
      restic_backup_paths:
        - /etc/ssh
        - /etc/ufw
        - /etc/openvpn
        - /etc/systemd/system
        - /home/debian/.hermes/config.yaml
        - /home/debian/.hermes/.env
        - /home/debian/OrchestrationOasis
        - /home/debian/authentik
        - /home/debian/openbao
        - /home/debian/netbox
        - /home/debian/semaphore
        - /home/debian/.semaphore
      restic_exclude_patterns:
        - /home/debian/.hermes/hermes-agent/**
        - /home/debian/.hermes/node/**
        - /home/debian/.hermes/image_cache/**
        - /home/debian/.hermes/audio_cache/**
        - /home/debian/.hermes/session_db/**
        - /home/debian/.hermes/logs/**
        - /home/debian/.hermes/chats/**
        - /home/debian/OrchestrationOasis/.git/**
        - /home/debian/OrchestrationOasis/.venv/**
        - /home/debian/OrchestrationOasis/.trivy-cache/**
```

Only include paths that exist. `/home/debian/.semaphore` contains the live
Semaphore SQLite state; `/home/debian/semaphore` alone only protects deployment
assets. Repository data, caches, pCloud mounts, Docker layers, and rebuildable
artifacts such as `.venv` and `.trivy-cache` should not be recursively backed
up.

## Deployment and first run

The password file and repository must already exist. The role refuses to run if
it cannot decrypt the configured repository and never calls `restic init`.
Bootstrap any new repository once from a protected administrative session after
verifying the exact rclone remote and destination path; do not leave repository
initialization or password material in routine CI.

Preview and apply the role:

```bash
cd ansible
ansible-playbook playbooks/install_restic.yml \
  --inventory inventories/production/hosts.yml --check --diff
ansible-playbook playbooks/install_restic.yml \
  --inventory inventories/production/hosts.yml
```

The role validates and enables the timer but deliberately does not trigger a
backup. Validate the final configuration, then start the first run manually:

```bash
sudo systemctl start infraforge-backup.service
sudo systemctl status infraforge-backup.service --no-pager
sudo /usr/local/sbin/infraforge-backup-audit.sh
```

A run is healthy only if the service succeeded, a recent snapshot exists, and
`restic list locks` is empty.

## Restore drill

Never begin with an in-place restore. List snapshots and restore into an isolated
directory first:

```bash
sudo bash -lc 'set -a; source /root/.config/restic/infraforge.env; set +a; restic snapshots'
sudo install -d -m 0700 /var/tmp/restic-restore-test
sudo bash -lc 'set -a; source /root/.config/restic/infraforge.env; set +a; restic restore latest --target /var/tmp/restic-restore-test --include /etc/ssh'
sudo diff -ruN /etc/ssh /var/tmp/restic-restore-test/etc/ssh
sudo rm -rf /var/tmp/restic-restore-test
```

Use a specific snapshot ID for an actual incident. Check ownership, modes,
application version, and service dependencies before copying restored data into
place.

## Application consistency

Production enables a fail-closed preparation hook before every Restic snapshot.
It creates a root-only atomic generation under `/var/backups/infraforge` with:

- NetBox and Authentik PostgreSQL custom-format dumps produced by each database
  container and validated with the matching `pg_restore --list`;
- a NetBox media archive;
- a Semaphore SQLite online backup validated with `PRAGMA integrity_check`;
- Hermes `state.db` and `kanban.db` SQLite online backups, each validated with
  `PRAGMA integrity_check`;
- a root-only Hermes data archive containing configuration, provider OAuth,
  memories, skills, cron definitions, canonical session metadata, and the
  WhatsApp linked-device session;
- an OpenBao Raft snapshot fetched through a dedicated least-privilege AppRole
  and validated from its archive structure, internal SHA-256 manifest, Raft
  metadata, and expected metadata fields;
- SHA-256 checksums, a non-secret manifest, and a `COMPLETE` marker.

NetBox application and worker containers are stopped for the
short interval covering both its PostgreSQL dump and media archive, then started
again before the other exports continue. An EXIT/signal trap restarts every
writer that the hook stopped. This brief maintenance window gives the database
and media archive one coherent writer-free boundary.

The Hermes user gateway is stopped for the short interval covering both SQLite
copies and the data archive. The hook tracks whether it stopped the gateway and
restarts it in the normal path and in the EXIT/signal cleanup path. Rebuildable
runtime data (`hermes-agent`, Node, LSP binaries, caches, logs, and update
snapshots) is intentionally excluded; reinstall Hermes before or after restoring
the persistent data bundle.

The hook accepts a stable running gateway or a proven quiescent user-service
state. Quiescent means `ActiveState` is `inactive` or `failed` **and** both
`MainPID` and `ControlPID` are zero. A D-Bus failure, unknown unit, transitional
state, or residual process fails the backup before any Hermes file is read. A
non-zero `systemctl stop` result is accepted only when the subsequent PID-based
check proves quiescence.

The hook publishes a generation only after every validation succeeds. Any dump,
TLS, authorization, container, disk, or integrity failure stops the service
before `restic backup`, `forget`, or `prune` runs. Files and directories use
root-only permissions. A previous generation is never silently reused as the
current backup.

Provision the OpenBao identity once from a protected root session:

```bash
sudo python3 scripts/provision-openbao-backup-approle.py
sudo stat -c '%U:%G %a' /root/.config/openbao/backup-approle.json
```

The file must report `root:root 600`. The tool reconciles policy and TTL
settings, validates an existing identity, and never prints role or secret IDs.
The resulting token has only `read` capability on
`sys/storage/raft/snapshot`; administrative endpoints must return HTTP 403.

The AppRole SecretID is a long-lived machine credential protected by root-only
permissions. Rotate and revoke it explicitly with:

```bash
sudo python3 scripts/provision-openbao-backup-approle.py --rotate
sudo systemctl start infraforge-backup.service
```

### Artifact restore validation

Restore one complete generation into an isolated directory, never over live
services. Require `COMPLETE`, then validate:

```bash
sha256sum --check SHA256SUMS
pg_restore --list netbox.postgresql.dump
pg_restore --list authentik.postgresql.dump
tar -tf netbox-media.tar
python3 - <<'PY'
import sqlite3
db = sqlite3.connect('file:semaphore.sqlite3?mode=ro', uri=True)
assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
PY
python3 - <<'PY'
import sqlite3
for path in ('hermes-state.sqlite3', 'hermes-kanban.sqlite3'):
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
PY
tar -tf hermes-files.tar
```

### Hermes disaster recovery

Restore a complete generation from Restic into an isolated directory first,
then use the installed root-only helper. An alternate target is safe for a
restore drill and does not require stopping production:

```bash
sudo install -d -o debian -g debian -m 0700 /var/tmp/hermes-restore-drill
sudo infraforge-hermes-restore.sh \
  /path/to/restored/generation \
  /var/tmp/hermes-restore-drill
```

For an actual recovery, reinstall Hermes without running the gateway, stop the
user gateway, restore into `/home/debian/.hermes`, run diagnostics, and start it:

```bash
sudo systemctl --user --machine=debian@.host stop hermes-gateway.service
sudo infraforge-hermes-restore.sh /path/to/restored/generation
sudo -u debian hermes doctor
sudo systemctl --user --machine=debian@.host start hermes-gateway.service
```

The helper refuses a production restore while the gateway is active. It requires
the generation `COMPLETE` marker, validates every generation checksum, rejects
unsafe tar members, requires the memory, auth and WhatsApp identity files,
removes stale managed paths, and checks both databases before and after
installation. It canonicalizes the target and binds an existing target to its
device/inode identity. All managed-path mutations use stable directory descriptors,
`O_NOFOLLOW`, and relative `dir_fd` renames; no privileged mutation re-resolves a
user-controlled nested path. Existing managed paths are journaled before each
rename into a root-only rollback tree. Signals trigger descriptor-relative rollback;
a fully recovered transaction is cleaned automatically, while evidence from an
incomplete rollback is deliberately preserved for manual recovery. A production
restore proceeds only when the user-service manager proves the gateway is
quiescent (`inactive` or `failed`, with both service PIDs zero).
The target must already exist as a real directory. The generation path must be
canonical, root-owned, and non-writable by group or other users, including every
ancestor and checksum-listed artifact. Temporary transaction trees are created
under root-owned sticky `/var/tmp`; the helper refuses the restore unless `/var/tmp`
and the target are on the same filesystem so descriptor-relative renames remain
atomic. Managed archive entries must be unique and may not overlap as parent/child
paths.
The Restic repository password and rclone configuration remain
separate root-only recovery prerequisites; back them up through the secrets
recovery process as well.

Artifact validation is not a full disaster-recovery exercise. PostgreSQL dumps
must also be restored into disposable containers matching PostgreSQL 18 for
NetBox and PostgreSQL 16 for Authentik. OpenBao needs a disposable 2.5.5 node,
independent recovery material, `raft snapshot restore -force`, unseal, and
canary checks. Never test these restores against production.

The 2026-07-16 restore drill exercised the NetBox dump on disposable PostgreSQL
18, the Authentik dump on disposable PostgreSQL 16, SQLite integrity, all outer
checksums, and the NetBox media archive restored from pCloud. The OpenBao archive
and its internal checksums were validated; the isolated OpenBao restore remains
an explicit validation-backlog item.

## Migrating from Duplicati

Removing the Duplicati role from Git does not delete a previously deployed
container or its data. Confirm Restic backup and restore tests first, then stop
and remove Duplicati deliberately on each affected host. Keep its old backup
repository until the Restic retention window and at least one restore drill have
completed.
