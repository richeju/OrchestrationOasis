# Orchestration Oasis

Orchestration Oasis provisions a small self-hosted infrastructure with
[Ansible](https://docs.ansible.com/). It targets Debian hosts and keeps Windows
Chocolatey automation as a separate entry point.

The project favours explicit inventory groups, idempotent roles, manual
production deployments, and secrets supplied at runtime. No production host or
credential belongs in Git.

## Managed services

The complete Linux playbook can manage system updates, Docker, UFW, ZeroTier,
pCloud through rclone, Dashy, encrypted Restic backups, Prometheus, NetBox,
BIND, OpenBao, and YubiKey SSH authentication. A host receives only the roles
represented by its inventory groups.

## Quick start

Requirements: Git, Python 3.12 or newer with `venv`, GNU Make, an SSH
identity, and a Debian target reachable through SSH with non-interactive sudo.
Docker is required locally only for the Trivy security scan.

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
cp ansible/inventories/production/hosts.example.yml \
  ansible/inventories/production/hosts.yml
```

The example enables only the `linux` and `docker` groups. Opt in to other roles
after reviewing their prerequisites in [deployment](docs/deployment.md). Verify
connectivity, then preview a deployment:

```bash
cd ansible
ansible all --inventory inventories/production/hosts.yml --module-name ping
ansible-playbook site.yml \
  --inventory inventories/production/hosts.yml \
  --check --diff
```

Deploy one service by tag:

```bash
ansible-playbook site.yml \
  --inventory inventories/production/hosts.yml \
  --tags docker
```

Run all local quality checks from the repository root:

```bash
make check
```

## Secrets

Provide secrets with Ansible Vault or environment variables. The currently
supported deployment variables are:

- `PCLOUD_TOKEN`
- `NETBOX_DB_PASSWORD`
- `NETBOX_REDIS_PASSWORD`
- `NETBOX_SECRET_KEY`
- `NETBOX_API_ENDPOINT`
- `NETBOX_API_TOKEN`

The pCloud and NetBox roles fail before making changes when required secrets are
missing or clearly unsafe. Restic uses existing root-only credentials and never
receives its repository password from the standard deployment workflow. See
[deployment](docs/deployment.md) for GitHub environment setup.

## Repository layout

```text
ansible/
  inventories/example/       safe syntax-check inventory
  inventories/production/    ignored local production inventory
  playbooks/                  focused entry points
  playbooks/roles/            reusable service roles
  site.yml                    complete tagged orchestration
docs/                         architecture and operations
.github/workflows/            CI, manual deploy, maintenance
```

Further reading:

- [Architecture](docs/architecture.md)
- [Deployment and GitHub Actions](docs/deployment.md)
- [pCloud operations](docs/pcloud.md)
- [Restic backup and restore](docs/restic.md)
- [OpenBao operations](docs/openbao.md)
- [Semaphore operations](docs/semaphore.md)
- [Security notes](README.security.md)
- [Known technical debt](docs/technical-debt.md)
