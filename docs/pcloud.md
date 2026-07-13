# pCloud role

The pCloud role mounts a pCloud remote through rclone and a managed systemd
unit. It does not kill unrelated rclone processes or force-unmount filesystems
during normal convergence.

## Required configuration

Set `PCLOUD_TOKEN` in the execution environment or override `pcloud_token` with
an encrypted Ansible Vault value. Common non-secret variables include:

```yaml
pcloud_hostname: eapi.pcloud.com
pcloud_mount_point: /mnt/pcloud
pcloud_group: pcloud_users
pcloud_gid: 1001
```

## Behaviour

The role:

1. validates the token and mount path;
2. installs rclone and FUSE 3;
3. creates the access group and required directories;
4. writes the credential file with mode `0600`;
5. restarts the systemd unit only when configuration changes;
6. waits for `mountpoint` to confirm the remote is mounted.

## Troubleshooting

```bash
systemctl status rclone-pcloud.service
journalctl -u rclone-pcloud.service --since today
mountpoint /mnt/pcloud
```

If the mount is busy, stop the service and investigate open files before
unmounting. Avoid global `pkill rclone` commands because the host may manage
other rclone remotes.
