# Known technical debt

This file records issues that were found during the repository coherence review
but deliberately not changed without service-specific migration testing.

## High priority

### Mutable container images

Dashy, Duplicati, NetBox, Portainer, Prometheus, and ZeroTier still default to
`latest`; BIND, PostgreSQL, and Redis use broad mutable tags. Replacing them
requires identifying the versions currently deployed, reading each migration
path, testing persistent data, and then pinning tags or digests. Do not perform
a blind bulk update.

### k3s bootstrap provenance

The k3s role downloads and runs `get.k3s.io` without a pinned release or
checksum. Replace it with a versioned, checksum-verified installation before
using the role on a production cluster.

### NetBox topology and Redis authentication

The current compact stack omits NetBox worker and housekeeping services. It
also writes a Redis password variable without configuring Redis `requirepass`.
Adding workers or real Redis authentication requires coordinated testing
against the pinned NetBox release and existing data.

### Container exposure and host firewalling

Prometheus and Duplicati publish ports without a private bind address. Docker
published ports can also bypass assumptions made by UFW. Determine the intended
VPN/LAN/public reachability for every service before changing bind addresses or
the `DOCKER-USER` chain.

## Medium priority

- Portainer has read-write access to the Docker socket and therefore effective
  host-root capability.
- Most containers still lack explicit capability drops, read-only filesystems,
  resource limits, and `no-new-privileges`.
- Docker cleanup removes all unused images and can remove a local rollback
  image; add age filters and a retention policy.
- The dynamic NetBox inventory still uses environment/service composite groups;
  verify that real NetBox custom fields map to the groups used by `site.yml`.
- OpenBao audit-log rotation uses `copytruncate`; evaluate signal-based rotation
  if the deployed image and ownership model support reliable reopen semantics.
- Python direct dependencies are pinned, but transitive dependencies and hashes
  are not locked.

## Validation backlog

- Add `actionlint` to CI for workflow semantics.
- Render every Compose template with fixture variables and run
  `docker compose config`.
- Add Molecule or equivalent runtime/idempotence tests for Docker, UFW, BIND,
  NetBox, OpenBao, and YubiKey.
- Add health checks and post-deployment probes to older service roles.
- Document and test the separate Windows/Chocolatey entry points.
