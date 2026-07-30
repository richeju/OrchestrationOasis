# Daily autonomous repository maintenance

Hermes performs one bounded maintenance assessment per day for `richeju/OrchestrationOasis`. It may fix one demonstrated bug, implement one low-risk improvement, finish an existing daily PR, or explicitly abstain.

## Schedule and execution model

All times use `Europe/Paris`:

- `08:00`: deterministic VPS and UniFi security audit;
- `10:00`: launch the repository-maintenance worker;
- `10:45`: deliver the result if complete;
- `11:15`: fallback delivery if the first reporter was silent while work continued.

A normal Hermes cron-agent has a three-minute hard limit, which is too short for repository checks and GitHub CI. The 10:00 no-agent cron therefore launches a transient **user systemd service**. The service runs for at most 55 minutes and the nested Hermes command has a 50-minute timeout. Reporter jobs only read the bounded result file and deliver it verbatim; they never reason over or mutate the repository.

The versioned implementation is [`scripts/daily-repository-maintenance.py`](../scripts/daily-repository-maintenance.py). It is installed under three explicit names:

```text
/home/debian/.hermes/scripts/daily_repository_maintenance_launcher.py
/home/debian/.hermes/scripts/daily_repository_maintenance_worker.py
/home/debian/.hermes/scripts/daily_repository_maintenance_reporter.py
```

The source-of-truth mission prompt is [`automation/prompts/daily-repository-maintenance.md`](../automation/prompts/daily-repository-maintenance.md).

## Logs are first-class evidence

Candidate selection must account for messages and state from:

- the deterministic daily security audit;
- bounded journald warnings/errors over the last 24 hours;
- bounded Hermes gateway warnings/errors;
- Docker health and bounded recent logs only for a failing container;
- recent GitHub CI and Maintenance workflow status/failure logs;
- issues, technical debt, TODO/FIXME markers, and tests.

The worker records only a structured, sanitized pattern: component, count/severity, time window, and minimal message pattern. A log warning is not automatically a bug. The worker must reproduce or otherwise prove a root cause and distinguish expected noise, transient failures, stale messages, and physical-only interventions.

Raw authentication logs, request headers, query strings, client trails, usernames, session IDs, credentials, tokens, repository credentials, and complete log dumps are excluded from reports and PRs.

## Selection and Git lifecycle

Only one coherent action is allowed per day. Priority is:

1. reproducible bug or security/correctness issue shown by logs or CI;
2. demonstrated automation regression or flake;
3. missing regression test for an observed failure;
4. bounded parser/script robustness improvement;
5. factual documentation drift;
6. abstention.

The worker refuses to start from a dirty tree or a branch other than `main`. If a `daily/*` PR already exists, that PR is the only allowed task for the day. New work uses a `daily/YYYY-MM-DD-short-topic` branch, updates tests/documentation, and must pass targeted tests, `git diff --check`, `make check`, and `make scan` before publication.

Automatic merge is allowed only for a low-risk, reversible change with all required checks green and no unresolved review finding. GitHub merge never implies live deployment; the report must say `not deployed` unless live convergence was separately performed and verified.

## Prohibited autonomous changes

The worker cannot autonomously mutate:

- firewall, SSH, VPN, WAN/LAN, DNS, or UniFi;
- secrets, OpenBao policies, authentication data, or Restic repositories/restoration;
- storage, destructive migrations, or data deletion;
- service/Hermes reboot or shutdown;
- physical-only work such as `AUD-0-SW` adoption;
- infrastructure requiring an outage.

These require explicit human approval and a recovery plan.

## State and concurrency

State is stored mode `0700` under:

```text
/home/debian/.hermes/state/daily-repository-maintenance/
```

Daily running/result/delivered files are mode `0600`. An exclusive lock prevents concurrent workers. Reports are delivered once; the first reporter stays silent while a recent worker remains active, and the fallback reports a missing or overlong run.

## Validation

```bash
python3 scripts/tests/daily-repository-maintenance.test.py
make check
make scan
```

Tests cover dirty-tree refusal, bounded systemd launch, worker result handling, removal of Hermes CLI session metadata, one-time delivery, and silent/reported long-running states.
