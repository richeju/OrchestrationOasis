# OpenBao operations

Orchestration Oasis deploys OpenBao as a private, TLS-only service with
persistent integrated Raft storage. The repository contains configuration and
orchestration only; recovery keys, tokens, certificates, and Raft snapshots are
runtime secrets and must remain outside Git.

## Inventory example

```yaml
openbao:
  hosts:
    secrets-host:
      openbao_dir: /opt/openbao
      openbao_bind_address: 10.0.0.10
      openbao_api_address: 10.0.0.10
```

The server certificate must contain the configured API address in its SAN. Put
`ca.crt`, `server.crt`, and `server.key` in `<openbao_dir>/tls/` before running
the role, or enable `openbao_manage_tls` and reference controller-side files
that are explicitly excluded from Git.

## Preview and deployment

```bash
cd ansible
ansible-playbook playbooks/install_openbao.yml \
  --inventory inventories/production/hosts.yml \
  --check --diff
ansible-playbook playbooks/install_openbao.yml \
  --inventory inventories/production/hosts.yml
```

## Initialization and unseal

Initialization is intentionally not automated by this public role. Run it once
from a protected administrative session, capture output directly into a
root-only file, and distribute Shamir shares across independent encrypted or
offline locations. Never print initialization output in CI logs.

After a restart, an instance using Shamir seal remains sealed until the required
threshold of shares is submitted. Verify status through the health endpoint;
HTTP 200 means active and unsealed, while 501 commonly means uninitialized and
503 commonly means sealed.

## Backup

Create regular Raft snapshots with a dedicated least-privilege backup identity.
Encrypt and copy snapshots off-machine. Keep the recovery material separate
from the snapshot so compromise of one location does not provide both pieces.
Test restoration on an isolated instance before relying on the backup chain.

## Migration policy

Migrate one consumer at a time:

1. write and read back a pilot secret using a scoped identity;
2. update the consumer to fetch from OpenBao;
3. verify service operation and rotation;
4. only then remove the legacy local secret file.
