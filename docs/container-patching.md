# Weekly host and container patching

The weekly maintenance job updates Debian packages and the Docker Compose stacks for Authentik and NetBox. Semaphore is a separate host service and is not redeployed by this procedure.

## Source of truth

The versioned implementation is [`scripts/sunday-container-patching.sh`](../scripts/sunday-container-patching.sh). Hermes executes a deployed copy from:

```text
/home/debian/.hermes/scripts/sunday_container_patching.sh
```

After modifying the versioned script, run the regression tests, deploy it with mode `0755`, compare its checksum with the repository copy, and keep the Hermes cron job pointed at the deployed filename.

## Health-check behavior

After `docker compose pull` and `docker compose up -d`, the script waits for every Compose container:

- `running` with `healthy`: ready;
- `running` without a Docker healthcheck (`none`): ready;
- `running` with `starting`: retry until the bounded timeout;
- `unhealthy`, stopped, missing, or an unknown health state: fail immediately;
- still `starting` after the timeout: fail with the last observed state.

Defaults:

- timeout: `300` seconds;
- polling interval: `10` seconds.

They can be overridden for controlled tests with `HEALTH_TIMEOUT_SECONDS` and `HEALTH_POLL_SECONDS`.

## Verification

Run the isolated behavior tests:

```bash
./scripts/tests/container-patching.test.sh
```

The test covers `starting` to `healthy`, timeout, `unhealthy`, and a stopped container. The full repository validation includes it through:

```bash
make check
make scan
```

Do not trigger the complete maintenance job merely to test polling: it performs real APT upgrades and Docker pulls. Validate the deployed script with syntax/checksum checks and read-only inspection of current container health; let the next scheduled maintenance exercise the full mutation path.
