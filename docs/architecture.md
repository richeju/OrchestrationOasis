# Architecture

## Design principles

Orchestration Oasis separates configuration from infrastructure identity:

- roles describe how to converge one service;
- playbooks bind a role to an inventory group;
- `site.yml` imports the Linux playbooks in dependency order;
- inventories decide which services a host receives;
- runtime environment variables or Ansible Vault provide secrets.

The repository's default inventory is deliberately empty and exists only for
discovery, linting, and syntax checks. Production deployments always require an
explicit inventory, so an unqualified `ansible-playbook site.yml` targets zero
hosts.

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
`hermes`, `prometheus`, `netbox`, `semaphore`, `bind_dns`, and `yubikey`.
`openbao` is the private secrets-service group and should only target hosts
reachable through a trusted administration network.
`infraforge_vps` is reserved for the read-only production audit and carries its
non-secret probe topology through playbook-relative group variables.

Windows hosts remain outside `site.yml` and use the dedicated Chocolatey
playbooks.

## Execution control plane

GitHub is the source of versioned automation. Semaphore checks out this
repository and provides inventories, templates, schedules, and run logs. AWX is
not part of the current architecture because it would duplicate Semaphore's
orchestration role. See [Semaphore operations](semaphore.md).

The authoritative boundary between managed and merely observed services is the
[current infrastructure state](current-state.md). A role present in the tree is
not sufficient evidence that it owns the corresponding live service.

## Safe evolution

Add a new service by creating a role, a focused playbook, an inventory group,
and a tagged import in `site.yml`. Add a post-deployment validation to the role
so a successful Ansible run also means the service is usable.
