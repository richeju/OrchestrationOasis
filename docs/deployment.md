# Deployment

## Local prerequisites

The controller requires Git, Python 3.12 or newer, the Python `venv` module,
GNU Make, and an SSH identity accepted by the targets. Targets must be Debian
hosts with Python installed and an account allowed to use `sudo` without an
interactive password prompt. Host-key checking is enabled.

The Docker CLI with Compose v2 is required by the rendering tests in
`make check`; those `docker compose config` calls do not contact the daemon.
Docker daemon access is additionally required for `make scan`, directly or
through passwordless `sudo`; that target runs both `pip-audit` and a
digest-pinned Trivy image. Trivy always scans secrets and scans vulnerabilities
or misconfigurations when it recognizes a supported manifest.

Prepare the controller and verify connectivity:

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
cp ansible/inventories/production/hosts.example.yml \
  ansible/inventories/production/hosts.yml
cd ansible
ansible all --inventory inventories/production/hosts.yml \
  --module-name ping
```

## Inventory groups and dependencies

A role is applied only to hosts in its inventory group. The production example
enables only the low-risk `linux` and `docker` groups; opt in to every other
group explicitly.

| Group | Required dependencies or preparation |
| --- | --- |
| `linux` | Debian target and passwordless non-interactive sudo |
| `docker` | `linux` host; installs the Docker Engine |
| `ufw` | Console or recovery access before changing firewall policy |
| `dashboard` | Docker and an existing `zt*` ZeroTier interface |
| `netbox` | Legacy compact stack only; explicit confirmation required; not the live official stack |
| `bind_dns` | Docker, ZeroTier, reachable NetBox API, API endpoint and token |
| `prometheus` | Docker and an explicit loopback/private bind address |
| `zerotier` | Docker |
| `restic` | Root-only rclone config, repository password file, explicit source paths |
| `hermes` | Existing Hermes account and required private files; read `hermes.md` before opt-in |
| `pcloud` | Valid rclone pCloud token |
| `openbao` | Docker and TLS CA/certificate/key already provisioned or supplied |
| `yubikey` | At least one tested U2F mapping and an out-of-band recovery session |
| `infraforge_vps` | Read-only audit target; no deployment role |

Membership in a service group does not automatically add the host to every
prerequisite group. BIND includes the Docker role itself, but it still requires
an operational ZeroTier interface and NetBox API.

## Check mode and first deployment

Start with check mode:

```bash
ansible-playbook site.yml \
  --inventory inventories/production/hosts.yml \
  --check --diff
```

Check mode is a preview, not a transaction or a complete integration test.
Command-backed services cannot always predict changes. A first OpenBao check
also requires Docker and the destination TLS files to exist because no service
can be probed before those prerequisites are present. Run `make check` for
syntax and static validation, then apply one tag at a time on new hosts.

## GitHub deployment runner

The `Deploy` and `Maintenance` workflows require a dedicated self-hosted runner
with access to the private production network. Do not attach a shared runner or
a runner available to untrusted repositories.

The runner must have:

- outbound access for Python and Ansible dependencies;
- SSH connectivity and trusted `known_hosts` entries for every target;
- a dedicated SSH identity with the minimum required privileges;
- Python 3.13 support and non-interactive sudo on the managed targets;
- repository access restricted to approved maintainers;
- operating-system updates and monitoring independent of this repository.

Both workflows use the same `production-operations` concurrency group, so a
maintenance run cannot overlap a deployment. The private inventory is written
to `RUNNER_TEMP` with mode `0600` and removed with an `always()` cleanup step.
An ephemeral runner is still preferred.

Configure the protected `production` GitHub environment with required reviewers
and these repository or environment secrets:

- `ANSIBLE_INVENTORY`: complete production inventory in YAML;
- `PCLOUD_TOKEN`: required by pCloud;
- `NETBOX_DB_PASSWORD`, `NETBOX_REDIS_PASSWORD`, `NETBOX_SECRET_KEY`: NetBox;
- `NETBOX_API_ENDPOINT`, `NETBOX_API_TOKEN`: BIND and dynamic inventory access;

The standard workflow never transmits a Restic repository password. Restic
requires an existing root-owned `0600` password file and initialized repository.
One-time provisioning must happen through a protected administrative session,
not a routine CI deployment.

The deploy workflow defaults to check mode. Check and apply are separate runs:
record the commit SHA shown by GitHub and confirm it has not changed before
applying. Mutable container tags can also change between runs; see
[technical debt](technical-debt.md).

The deploy job is skipped unless the workflow runs from `main`. Keep the
`production` environment protected by independent required reviewers because
repository code alone cannot protect secrets from a maintainer who can modify a
workflow on an arbitrary branch.

## Maintenance

The weekly workflow performs system upgrades and Docker cleanup. It uses the
same protected environment, private inventory, runner, and concurrency lock as
deployment. Review its impact before enabling the schedule: package upgrades
and removal of unused images can reduce local rollback options.

## Rollback

Ansible convergence is not a backup. Pin tested container versions in inventory,
back up persistent volumes and OpenBao Raft snapshots off-machine, and record
the last known-good Git commit before production changes. To roll back
configuration, check out that commit and run only the affected tag.
