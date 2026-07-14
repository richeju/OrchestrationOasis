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
      restic_exclude_patterns:
        - /home/debian/.hermes/hermes-agent/**
        - /home/debian/.hermes/node/**
        - /home/debian/.hermes/image_cache/**
        - /home/debian/.hermes/audio_cache/**
        - /home/debian/.hermes/session_db/**
        - /home/debian/.hermes/logs/**
        - /home/debian/.hermes/chats/**
        - /home/debian/OrchestrationOasis/.git/**
```

Only include paths that exist. Repository data, caches, pCloud mounts, Docker
layers, and rebuildable artifacts should not be recursively backed up.

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

Restic protects files, not live database consistency. PostgreSQL-backed NetBox
and Authentik require database dumps or native backup hooks before the filesystem
snapshot. OpenBao should use an authenticated Raft snapshot. These hooks must be
implemented and restore-tested separately; copying live database or Raft files
alone is not a complete recovery plan.

## Migrating from Duplicati

Removing the Duplicati role from Git does not delete a previously deployed
container or its data. Confirm Restic backup and restore tests first, then stop
and remove Duplicati deliberately on each affected host. Keep its old backup
repository until the Restic retention window and at least one restore drill have
completed.
