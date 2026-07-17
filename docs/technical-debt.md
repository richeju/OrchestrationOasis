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

### Preview and idempotence gaps

Semaphore intentionally skips file preparation and migration runtime in check
mode, so `--check --diff` is not a complete preview of that migration. BIND
derives zone serials from the current epoch and therefore rewrites zones and
restarts on otherwise identical convergence. Restic and Hermes also perform
some cache, package, or directory preparation before all destructive-safety
preconditions have been evaluated. Reorder those preflights and add a second
convergence test before treating check mode or idempotence as proven.

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
- The Debian bootstrap trusts Docker's repository key from TLS transport without
  verifying an expected fingerprint; pin and verify the vendor key during the
  next bootstrap hardening pass.

## Validation backlog

- Automate the already exercised disposable PostgreSQL 18 and 16 restore drill
  in a periodic job and extend its smoke queries to application-level canaries.
- Exercise an OpenBao Raft restore on a disposable 2.5.5 node with independent
  recovery material; archive and checksum validation alone is not a restore test.
- Automate the exercised Hermes generation restore, SQLite integrity checks,
  interrupted-transaction rollback, and hostname-filtered Restic audit fixture.
- Add an end-to-end disposable `restic backup` and `restic restore` test; current
  repository tests validate rendering and application hooks, not the entire
  repository transport.
- Extend the current Compose rendering suite to every remaining service role.
- Add Molecule or equivalent runtime/idempotence tests for Docker, UFW, BIND,
  NetBox, OpenBao, and YubiKey.
- Add health checks and post-deployment probes to older service roles.
- Document and test the separate Windows/Chocolatey entry points.
