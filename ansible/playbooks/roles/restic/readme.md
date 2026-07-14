# Restic backup role

Configures encrypted, unattended Restic backups over an existing rclone pCloud
remote. Restic performs encryption and snapshotting; rclone is transport only.
No FUSE mount or web interface is required.

## Safety model

- existing repositories and root-only credential files are reused by default;
- the role never initializes a repository;
- an existing password file is never replaced, even if an environment variable
  is accidentally present;
- every source path must be selected explicitly and must exist;
- the role probes pCloud, the repository, and stale locks before completing;
- installing the role enables the timer but does not start an immediate backup.

## Required variables

```yaml
restic_backup_paths:
  - /etc/ssh
  - /etc/ufw
  - /home/admin/service-config
```

The defaults match the established Infraforge repository and root-only files:

- repository: `rclone:pcloud-backup:Backups/infraforge-vps`;
- rclone config: `/root/.config/rclone/rclone.conf`;
- password: `/root/.config/restic/infraforge-repo.pass`;
- environment: `/root/.config/restic/infraforge.env`;
- timer: `infraforge-backup.timer`.

Override these values for another host. Initialize a new repository manually
from a protected administrative session. One-time password-file provisioning
also requires `restic_provision_password_file: true`; it refuses to run when the
target file already exists. Rotate repository keys with `restic key`, never by
replacing the password file.

## Retention and verification

Defaults retain seven daily, four weekly, and six monthly snapshots. Each run
performs `forget --prune`, a random `5%` data-subset check, and a stale-lock check.
See [the operations guide](../../../../docs/restic.md) for first-run and restore
procedures.
