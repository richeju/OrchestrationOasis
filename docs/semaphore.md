# Semaphore operations

Semaphore is the single Ansible execution UI for this environment. AWX is not
part of the architecture: running both would duplicate repository checkout,
inventory, credentials, scheduling, logs, and job-template management.

## Current deployment

- UI: `http://10.78.0.1:3001`
- exposure: VPN address only
- service: `semaphore.service`
- execution user: `debian`
- database: local SQLite
- canonical project repository:
  `https://github.com/richeju/OrchestrationOasis.git`

Semaphore clones the repository before a task run. GitHub is the source of code;
Semaphore's database stores its local users, credentials, orchestration
metadata, schedules, and execution history.

## Initial read-only template

The `VPS read-only audit` template runs:

```text
ansible/playbooks/audit_vps.yml
```

Its local inventory places the VPS in the `linux` group with
`ansible_connection=local`. The playbook makes no configuration changes. It
checks:

- required systemd services and failed units;
- VPN-only NetBox, Authentik, Semaphore, and OpenBao endpoints;
- OpenBao initialization and seal state;
- the installed Restic audit, snapshot count, and locks.

Run the template manually and inspect its task output before adding a schedule.
A failed audit must remain a report, not an automatic remediation trigger.

## Responsibilities

```text
GitHub repository -> versioned playbooks and roles
Semaphore         -> checkout, inventory, task templates, schedules and logs
Ansible           -> execution on the selected inventory
NetBox            -> future dynamic source of truth
OpenBao           -> machine secrets
```

Do not store infrastructure credentials in Git or duplicate OpenBao secrets in
Semaphore variable groups. When a playbook needs a secret, give its runner a
scoped OpenBao identity and fetch only the required path at execution time.

## AWX compatibility

AWX and Semaphore can execute the same Ansible repository independently, but
Semaphore should not call AWX job templates in this small deployment. Such a
chain adds two APIs, two credential stores and two audit trails without adding
execution capability. If a future migration to AWX is justified, migrate the
repository, inventories and templates from Semaphore rather than operating both
as nested orchestrators.

## Validation

On the VPS:

```bash
systemctl status semaphore --no-pager
curl --fail http://10.78.0.1:3001/
```

In Semaphore, confirm that a task starts by cloning the GitHub repository and
finishes with `Restic status: ok` and `Restic locks: 0`.
