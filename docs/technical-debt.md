# Known technical debt

This file records issues that were found during the repository coherence review
but deliberately not changed without service-specific migration testing.

## High priority

### Mutable container images

Dashy, NetBox, Prometheus, and ZeroTier still default to
`latest`; BIND, PostgreSQL, and Redis use broad mutable tags. Replacing them
requires identifying the versions currently deployed, reading each migration
path, testing persistent data, and then pinning tags or digests. Do not perform
a blind bulk update.

### NetBox production topology

The guarded compact role now authenticates Redis and renders coherent secrets,
but it still does not model the official production stack with workers,
PostgreSQL 18 and Valkey. Reconcile or replace the role only after database,
media, restore and rollback tests against a production-shaped fixture.

### Container exposure and host firewalling

Prometheus now refuses wildcard publication by default. Docker-published ports
can still bypass assumptions made by UFW. Determine the intended VPN/LAN/public
reachability for every service before changing the `DOCKER-USER` chain.

## Medium priority

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

- Extend the current Compose rendering suite to every remaining service role.
- Add Molecule or equivalent runtime/idempotence tests for Docker, UFW, BIND,
  NetBox, OpenBao, and YubiKey.
- Add health checks and post-deployment probes to older service roles.
- Document and test the separate Windows/Chocolatey entry points.
