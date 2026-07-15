# Semaphore operations

Semaphore is the single Ansible execution UI for this environment. AWX is
intentionally absent.

## Deployment

- UI: `http://10.78.0.1:3001`
- exposure: VPN address only
- runtime: Docker Compose
- image: `semaphoreui/semaphore:2.18.12`, pinned by digest in role defaults
- Compose project: `/home/debian/semaphore/compose.yml`
- role: `ansible/playbooks/roles/semaphore`
- playbook: `ansible/playbooks/install_semaphore.yml`
- persistent SQLite state: `/home/debian/.semaphore`
- canonical automation repository:
  `https://github.com/richeju/OrchestrationOasis.git`

Deploy with an explicit production inventory:

```bash
ansible-playbook \
  ansible/playbooks/install_semaphore.yml \
  --inventory ansible/inventories/production/hosts.yml
```

Check mode validates the image, network, paths, existing native configuration,
and SQLite prerequisites. It deliberately does not generate keys, write
configuration, stop systemd, or start Compose. Runtime rendering is covered by
`scripts/tests/semaphore-role.test.sh`; apply mode performs health and rollback
validation.

The role migrates the earlier native systemd deployment in place. It stops the
native unit, creates a cold SQLite backup, changes state ownership for the
container user, starts the Compose service, checks the VPN endpoint, and only
then disables the native unit. During the initial migration, its rescue block
first proves that the container stopped, restores the cold database and UID 1000
ownership, and then restarts the native service. Later container updates never
start the native service automatically.

## Container hardening

The Compose deployment:

- binds only to `10.78.0.1:3001`;
- pins the official image by SHA-256 digest;
- runs as the image's unprivileged UID 1001;
- drops all Linux capabilities;
- enables `no-new-privileges`;
- uses a read-only root filesystem;
- exposes only state and temporary working directories as writable mounts;
- does not mount the Docker socket;
- limits local JSON logs;
- includes an HTTP health check.

The live database and generated configuration are mode `0600`. They and the
runner private key stay outside Git.

## Runner access to the VPS

A local Ansible connection inside a container would target the container rather
than the VPS. The role therefore generates a dedicated Ed25519 runner key and
allows it from the fixed Docker subnet `172.30.0.0/24` only. The authorized-key
entry disables forwarding, agent use, X11, PTY allocation, and user rc files.

The Semaphore inventory connects to `10.78.0.1` as `debian`, uses the mounted
runner key, and verifies the pinned host key. Passwordless sudo on the VPS is
still required for playbooks using `become`.

The complete inventory payload is versioned at
`ansible/inventories/semaphore-vps.example.yml`. Copy that YAML into the
Semaphore inventory instead of using `ansible_connection=local`.

## Read-only audit template

The `VPS read-only audit` template runs:

```text
ansible/playbooks/audit_vps.yml
```

It checks required systemd services, failed units, NetBox, Authentik,
Semaphore, OpenBao, and Restic. It must finish with `changed=0`, `failed=0`,
`Restic status: ok`, and `Restic locks: 0`.

Run audit templates manually before adding schedules. An audit failure remains
a report and must not trigger automatic remediation.

## Data and backups

Important paths are:

```text
/home/debian/.semaphore/semaphore.db
/home/debian/semaphore/config/config.json
/home/debian/semaphore/runner/id_ed25519
/home/debian/semaphore/backups/semaphore.db.pre-docker
```

The initial migration backup is a cold SQLite copy. For a current application
backup, use SQLite's backup API or stop the Compose service before copying the
live database. Do not commit database, configuration, or key material.

Validate a database copy with:

```bash
sqlite3 /path/to/semaphore.db 'PRAGMA integrity_check;'
```

## Validation

```bash
sudo docker compose -f /home/debian/semaphore/compose.yml ps
sudo docker inspect semaphore --format '{{.State.Health.Status}}'
curl --fail http://10.78.0.1:3001/
systemctl is-enabled semaphore
```

Expected results are a healthy container, a successful HTTP probe, and a
disabled native unit.

## Emergency rollback

The role performs this rollback automatically when migration validation fails.
For a manual rollback:

1. stop the Compose project;
2. restore ownership of `/home/debian/.semaphore` to UID/GID `1000:1000`;
3. enable and start `semaphore.service`;
4. verify `http://10.78.0.1:3001` and API login.

Do not run the native service and container at the same time: they share the
same SQLite state and TCP port.
