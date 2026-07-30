# Daily repository maintenance

## Purpose

Run one bounded maintenance candidate every day for `richeju/OrchestrationOasis`, using recent operational signals to prioritize a bugfix, test improvement, or documentation improvement.

The system is intentionally **PR-only**:

- no automatic merge;
- no deployment;
- no direct infrastructure mutation;
- no execution of model-authored code on the VPS;
- no raw logs or model-authored prose delivered to WhatsApp.

A human review and green GitHub-hosted CI remain mandatory.

## Schedule

All times use `Europe/Paris`:

- **10:00** — a no-agent cron script starts a bounded transient user-systemd worker;
- **11:00** — a no-agent cron script reads and delivers the deterministic result.

The worker has a 50-minute internal timeout. systemd enforces a 55-minute outer limit, kills the full control group, caps memory at 3 GiB, and caps tasks. The report is produced once; the implementation does not claim that WhatsApp delivery succeeded merely because the reporter printed output.

## Security model

### Deterministic host controller

`scripts/daily-repository-maintenance.py` performs only fixed operations:

1. require the canonical checkout to be clean and on `main`;
2. fetch `origin/main`, validate the expected HTTPS remote, and pin its immutable commit SHA;
3. stop if an open `daily/*` PR already exists;
4. create a disposable worktree under `/dev/shm/infraforge-daily-maintenance/<date>`;
5. collect bounded aggregate evidence;
6. run Hermes with all model tools routed into an air-gapped Docker sandbox;
7. discard model stdout/stderr;
8. remove the evidence file;
9. validate changed paths, file types, size, whitespace, and secret patterns against that pinned SHA without executing candidate code;
10. revalidate the canonical checkout/base, then build and push only an accepted candidate using filter-free Git plumbing;
11. open a PR with a fixed body and no auto-merge;
12. leave execution of the candidate to GitHub-hosted CI.

Commands are passed as argument arrays, never through a model-authored shell string. The branch name, commit message, PR title, and PR body are deterministic.

Host Git mutation is serialized by a separate repository lock. External diff/textconv drivers, hooks, and signing are disabled. Candidate bytes are staged with `hash-object --no-filters` plus `update-index`; the commit is built with `write-tree` and `commit-tree`, not porcelain `git add`/`git commit`.

### Hermes sandbox

The dedicated Hermes profile is `dailymaintainer`. It is created as a minimal `--no-skills` profile rather than cloned wholesale. Its configuration has no external skill directories or credential-file passthroughs. Before every launch, the controller fails closed if those settings appear or if any file exists under profile skills, plugins, upload/media/delegation caches, or legacy cache paths that Hermes would auto-mount. Its model process runs on the host only to call the provider. No skill is loaded for the run; the enabled model tools are limited to `terminal` and `file`, and both are routed through Hermes' Docker backend.

The sandbox has:

- `--network=none` through `TERMINAL_DOCKER_NETWORK=false`;
- no forwarded environment variables, literal Docker environment, extra Docker arguments, or skill/credential/cache data;
- a fresh per-process container;
- CPU and memory limits;
- a read-only container root filesystem, with only bounded tmpfs mounts for `/root`, `/tmp`, `/var/tmp`, and `/run`;
- only the disposable worktree mounted read-write;
- `.git` metadata mounted read-only;
- the aggregate evidence file mounted read-only;
- no canonical checkout, host home, SSH configuration, `gh` authentication, OpenBao data, or service sockets.

The worktree uses host tmpfs rather than the VPS root filesystem, limiting persistent disk-filling impact. The active Docker overlay is ext4-backed and cannot enforce Hermes' requested overlay quota, so the controller explicitly makes the container root filesystem read-only instead of relying on that unsupported quota.

The `debian` account does not receive Docker-group membership and the Docker socket is never mounted. Hermes finds a dedicated host-side `docker` wrapper through a fixed minimal `PATH`; the controller verifies exact wrapper content, owner, file mode `0700`, and parent-directory mode `0700` before launch. The wrapper only executes `/usr/bin/sudo -n /usr/bin/docker` with Hermes-generated backend arguments. Model commands remain inside the resulting container and cannot invoke the host wrapper.

### Evidence from logs and operations

The controller examines a bounded 24-hour window but **never passes raw messages to the model**.

It converts journal messages into fixed categories such as:

- authentication failure;
- connection failure;
- disk pressure;
- out-of-memory;
- permission denied;
- rate limit;
- segmentation fault;
- timeout;
- TLS failure;
- unhealthy service;
- other warning.

Only category counts, normalized unit families, Docker state counts, normalized GitHub workflow states, and an open-issue count enter `.daily-evidence.json`. Issue titles/bodies, CI logs, journal text, IP addresses, hostnames, usernames, URLs, and credentials do not enter the sandbox or repository changes.

This satisfies the requirement to use messages and logs as evidence while preventing prompt injection and sensitive-data copying.

## Candidate policy

The model may modify at most three **existing** files in these scopes:

- `docs/**/*.md`;
- `scripts/tests/**/*.py`;
- `scripts/tests/**/*.sh`;
- `scripts/daily-security-audit.py`.

Additional filename deny rules exclude maintenance, deployment, patching, reboot, backup, inventory, and safety-control paths. New files, symlinks, binary patches, workflow changes, Ansible, requirements, Makefiles, automation controls, and large diffs are rejected.

For a code change, the candidate must update an existing regression test. If no useful and provable task fits the policy, abstention is the correct daily result.

## Validation and publication

The VPS applies only non-executing checks to model-authored content:

- allowlisted existing paths only;
- no symlink or binary;
- at most 80 KiB and 800 diff lines;
- `git diff --check`;
- deterministic secret-pattern rejection.

The candidate is then pushed as `daily/YYYY-MM-DD-maintenance` and opened as a PR. GitHub Actions runs `make check` and security scanning on GitHub-hosted `ubuntu-latest` runners. The worker never merges the PR, even if CI passes.

A rejected or failed candidate worktree is retained in `/dev/shm/infraforge-daily-maintenance/<date>` until reboot or manual investigation. A successful or empty candidate worktree is removed, and cleanup failure is reported rather than hidden. If PR creation is ambiguous after push, the controller queries GitHub and otherwise attempts to delete the remote branch; any possible orphan is stated explicitly.

## State and idempotency

Private state lives under:

```text
~/.hermes/state/daily-repository-maintenance/
```

Daily files:

- `<date>.launching` — launcher reservation;
- `<date>.running` — worker active;
- `<date>.result` — deterministic WhatsApp report payload.
- `<date>.reported` — payload already emitted (not a delivery-success acknowledgment).

A filesystem lock serializes launcher, worker, and reporter state transitions; a second lock serializes repository preparation and publication for the full worker run. Repeated launcher invocations for the same day are no-ops once launching, running, result, or reported state exists. A deterministic result payload is emitted at most once.

## Runtime deployment boundary

The public repository intentionally does not write private Hermes profile or cron state. Runtime installation is an explicit out-of-band operator action after the reviewed repository change is merged:

1. create the dedicated `dailymaintainer` profile with `--no-skills`, configure only the selected model/provider authentication, and keep `skills.external_dirs` plus `terminal.credential_files` empty;
2. configure and validate the canonical repository's fetch and push URL as `https://github.com/richeju/OrchestrationOasis.git`, then pre-pull the reviewed Hermes Docker backend image;
3. install the exact documented Docker wrapper in `~/.hermes/bin/daily-maintenance/docker`, with both wrapper and parent directory mode `0700`;
4. copy the reviewed controller source to the three private entry-point paths with mode `0700`;
5. register exactly two private no-agent jobs at `0 10 * * *` and `0 11 * * *`;
6. compare checksums and inspect the registered schedules before enabling the first run.

Exact wrapper content:

```sh
#!/bin/sh
exec /usr/bin/sudo -n /usr/bin/docker "$@"
```

Read-only drift check:

```bash
sha256sum scripts/daily-repository-maintenance.py \
  ~/.hermes/scripts/daily_repository_maintenance_launcher.py \
  ~/.hermes/scripts/daily_repository_maintenance_worker.py \
  ~/.hermes/scripts/daily_repository_maintenance_reporter.py
stat -c '%a %U:%G %n' ~/.hermes/scripts/daily_repository_maintenance_*.py \
  ~/.hermes/bin/daily-maintenance ~/.hermes/bin/daily-maintenance/docker
hermes cron list
```

All four checksums must match, all private entry points must be owned by `debian` with mode `700`, and only the launcher and reporter are cron scripts. The worker is started by the launcher through systemd.

## Installed entry points

The same audited source is installed under three mode-specific names:

```text
~/.hermes/scripts/daily_repository_maintenance_launcher.py
~/.hermes/scripts/daily_repository_maintenance_worker.py
~/.hermes/scripts/daily_repository_maintenance_reporter.py
```

The cron scheduler executes the launcher and reporter in `no_agent` mode. The long-running worker is tracked by the user systemd manager and does not depend on the cron agent process remaining alive.

## Manual checks

```bash
# Run repository tests and scans for the controller itself
make check
make scan

# Inspect private state
find ~/.hermes/state/daily-repository-maintenance -maxdepth 1 -type f -print

# Inspect transient worker status
systemctl --user list-units 'infraforge-daily-maintenance-*'

# Inspect retained rejected candidates
find /dev/shm/infraforge-daily-maintenance -maxdepth 2 -type f -print
```

Do not run the worker manually from a dirty or non-`main` canonical checkout. For testing, use the dedicated test suite and a disposable fixture repository.
