# Architecture

## Design principles

Orchestration Oasis separates configuration from infrastructure identity:

- roles describe how to converge one service;
- playbooks bind a role to an inventory group;
- `site.yml` imports the Linux playbooks in dependency order;
- inventories decide which services a host receives;
- runtime environment variables or Ansible Vault provide secrets.

The repository's default inventory is deliberately local and exists only for
discovery, linting, and syntax checks. Production deployments always require an
explicit inventory.

## Execution flow

```text
inventory group -> focused playbook -> role -> handler -> validation task
                         |
                         +---- imported and tagged by site.yml
```

For example, hosts in the `pcloud` group are selected by
`playbooks/install_pcloud.yml`. The pCloud role installs its dependencies,
writes its configuration, restarts the unit only after a relevant change, and
verifies the resulting mount.

## Inventory groups

Linux baseline hosts belong to `linux`. Service groups correspond to tags in
`site.yml`: `docker`, `ufw`, `zerotier`, `pcloud`, `dashboard`, `restic`,
`prometheus`, `portainer`, `netbox`, `bind_dns`, `k3s`, and `yubikey`.
`openbao` is the private secrets-service group and should only target hosts
reachable through a trusted administration network.

Windows hosts remain outside `site.yml` and use the dedicated Chocolatey
playbooks.

## Safe evolution

Add a new service by creating a role, a focused playbook, an inventory group,
and a tagged import in `site.yml`. Add a post-deployment validation to the role
so a successful Ansible run also means the service is usable.
