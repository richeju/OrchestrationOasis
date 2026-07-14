# OpenBao role

Deploys a single-node OpenBao service with Docker Compose, integrated Raft
storage, mandatory TLS, a file audit device, and audit-log rotation.

The role deliberately does not initialize, unseal, or inject root tokens. Those
operations produce sensitive recovery material and remain explicit operator
steps documented in [the OpenBao operations guide](../../../../docs/openbao.md).

## Safety defaults

- image pinned to `openbao/openbao:2.5.5`;
- listener bound to `127.0.0.1` unless explicitly overridden;
- wildcard binds such as `0.0.0.0` are rejected;
- TLS certificates and keys must already exist on the host or be supplied from
  paths outside the repository;
- Raft data, audit logs, private keys, and initialization output never belong in
  Git.

## Main variables

- `openbao_dir`: deployment directory, default `/opt/openbao`;
- `openbao_bind_address`: loopback or private address used for the published API;
- `openbao_api_address`: address included in the certificate SAN;
- `openbao_manage_tls`: copy TLS material from controller-side source paths;
- `openbao_tls_*_source`: source paths used only when TLS management is enabled.
