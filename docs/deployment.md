# Deployment

## Local deployment

Copy `ansible/inventories/production/hosts.example.yml` to `hosts.yml` and edit
it locally. The destination is ignored by Git.

Always begin with check mode:

```bash
cd ansible
ansible-playbook site.yml \
  --inventory inventories/production/hosts.yml \
  --check --diff
```

Some command-backed services cannot fully predict changes in check mode. Review
the output, then rerun without `--check` when ready.

## GitHub deployment

The `Deploy` workflow is manual and protected by the `production` GitHub
environment. Configure that environment with required reviewers, then create
these repository or environment secrets:

- `ANSIBLE_INVENTORY`: the complete production inventory in YAML;
- `PCLOUD_TOKEN`: required when deploying pCloud;
- `NETBOX_DB_PASSWORD`, `NETBOX_REDIS_PASSWORD`, and `NETBOX_SECRET_KEY`:
  required when deploying NetBox.
- `DUPLICATI_WEB_PASSWORD`: required when deploying Duplicati;
- `DUPLICATI_SETTINGS_KEY`: optional Duplicati settings encryption key.

The workflow defaults to check mode. Choose a single target or `full`, inspect
the dry-run, and explicitly disable check mode to apply the same deployment.
Concurrent production deployments are serialized.

## Maintenance

The weekly `Maintenance` workflow applies the `apt` role to the `linux` group
and Docker cleanup to the `docker` group. It uses the same protected production
environment and private inventory as manual deployments.

## Rollback

Ansible converges configuration but is not a backup system. Pin container image
versions in inventory, back up persistent volumes, and record the last known
good Git commit before production changes. To roll back configuration, check
out that commit and run the affected tag again.
