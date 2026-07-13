# Orchestration Oasis

Orchestration Oasis provisions a small self-hosted infrastructure with
[Ansible](https://docs.ansible.com/). It targets Debian hosts and keeps Windows
Chocolatey automation as a separate entry point.

The project favours explicit inventory groups, idempotent roles, manual
production deployments, and secrets supplied at runtime. No production host or
credential belongs in Git.

## Managed services

The complete Linux playbook can manage system updates, Docker, UFW, ZeroTier,
pCloud through rclone, Dashy, Duplicati, Prometheus, Portainer, NetBox, BIND,
k3s, and YubiKey SSH authentication. A host receives only the roles represented
by its inventory groups.

## Quick start

Requirements: Python 3.12 or newer, GNU Make, and a Debian target reachable through SSH.

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
cp ansible/inventories/production/hosts.example.yml \
  ansible/inventories/production/hosts.yml
```

Edit the copied inventory, then preview a deployment:

```bash
cd ansible
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
- `DUPLICATI_WEB_PASSWORD`
- `DUPLICATI_SETTINGS_KEY` (optional)

The pCloud, NetBox, and Duplicati roles fail before making changes when their required
secrets are missing or clearly unsafe. See [deployment](docs/deployment.md) for
GitHub environment setup.

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
- [Security notes](README.security.md)
