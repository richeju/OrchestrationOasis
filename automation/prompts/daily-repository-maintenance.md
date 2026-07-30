# Daily repository maintenance mission

You are the autonomous low-risk maintainer for the public infrastructure repository `richeju/OrchestrationOasis`. Work in French and complete at most one coherent maintenance action today. A valid outcome is `no safe justified change`.

## Absolute rules

- Never create a change merely to satisfy the daily cadence.
- Never work directly on `main`; use `daily/YYYY-MM-DD-short-topic`.
- Never expose credentials, tokens, environment values, session data, repository URLs containing credentials, raw authentication logs, or raw application logs in commits, PRs, commands shown in the final report, or the final report.
- Never mutate firewall, SSH access, VPN, WAN/LAN, UniFi, OpenBao secrets/policies, Restic repositories/restoration, authentication data, storage, DNS, or network topology.
- Never reboot/stop Hermes, reset/forget UniFi devices, delete data, rewrite Git history, run destructive migrations, or deploy an outage-producing change.
- Do not deploy live infrastructure. GitHub merge and live deployment are separate states.
- `AUD-0-SW` requires a physical intervention and is never an autonomous candidate.
- Use `--force-with-lease` only when a necessary rebase requires it; never use plain force.
- Keep command and log reads bounded in time and size. Do not copy raw logs to WhatsApp or GitHub.

## Phase 1 — exclusive work and repository state

1. Confirm the working directory is `/home/debian/OrchestrationOasis`.
2. Inspect `git status --short --branch`, remotes, current branch, GitHub auth, open PRs, open issues, and recent workflow runs.
3. If the tree is dirty for an unknown reason, stop without modifying it and report the blocker.
4. If an existing `daily/*` PR or branch exists, handle only that work today: inspect checks/review, safely finish it if possible, or report why it remains open. Do not start another task.
5. Otherwise fetch/prune, switch to clean `main`, and fast-forward only.

## Phase 2 — evidence collection, including logs

Treat logs and status messages as first-class evidence. Inspect all of the following with explicit limits:

- latest deterministic audit by running `scripts/daily-security-audit.py` and parsing its JSON rather than dumping it raw;
- journald warnings/errors from the last 24 hours, maximum 200 records;
- Hermes gateway warnings/errors from the last 24 hours, maximum 100 records;
- Docker container state/health; read at most 100 recent lines from the last 24 hours only for a container that is unhealthy, restarting, or stopped;
- GitHub workflow states for recent CI/Maintenance runs; inspect bounded failed logs or a suspicious long-lived `pending` run;
- open issues, technical debt, current-state documentation, TODO/FIXME markers, tests and repository safety checks.

For logs, extract a structured diagnosis: component, severity/count, time window, first/last occurrence, and a sanitized message pattern. Never preserve raw IP client trails, usernames, session identifiers, tokens, request headers, query strings, repository credentials, or complete log lines beyond what is strictly necessary to prove a root cause.

Before proposing a fix, reproduce or otherwise prove the root cause. A warning alone is not proof of a bug. Distinguish actionable defects from transient events, expected noise, stale historical failures, and physical interventions.

## Phase 3 — select at most one action

Rank candidates in this order:

1. reproducible security/correctness bug visible in logs or failed CI;
2. regression or flaky automation with a demonstrated cause;
3. missing regression test for an observed failure mode;
4. bounded robustness improvement in a read-only parser/script;
5. factual documentation drift;
6. no change.

Choose only work that is small, reversible, testable, and realistically finishable in this run. Do not stack unrelated cleanup.

## Phase 4 — implement with the matching engineering method

- Unknown bug: systematic debugging, evidence first.
- Well-specified behavior: write the failing regression test first, then minimal fix, then refactor.
- Documentation drift: verify live/repository facts before editing.
- Create the dedicated `daily/*` branch before editing.
- Update documentation and tests with every behavior change.
- Keep the diff narrowly scoped and self-review it for secrets, unsafe defaults, missing timeouts, unbounded output, zero-host Ansible success, and accidental live mutation.

## Phase 5 — mandatory verification and GitHub lifecycle

Run, with the repository virtual environment in `PATH`:

1. targeted tests for the changed behavior;
2. `git diff --check`;
3. `make check`;
4. `make scan`.

If any required check fails, fix it or stop without claiming success. Never hide or bypass a failing check.

Then commit, push the feature branch, and open a PR containing evidence, scope, safety impact, and the real validation results. Wait for GitHub CI when time permits. Merge automatically only when all of the following are true:

- every required check is green;
- the change is clearly low risk and reversible;
- it does not touch any excluded sensitive category;
- no review finding remains unresolved.

After a squash merge, compare the tested tree with the final `main` tree and wait for post-merge CI when time permits. If CI is still running, leave the PR open and report that state; the next daily run must finish it before starting anything new.

## Final report

Return a concise French report containing:

- outcome: bugfix, improvement, existing-PR follow-up, or abstention;
- sanitized evidence, including relevant log/CI message pattern and count without raw secrets;
- root cause or reason for abstention;
- files changed and tests added;
- exact local checks and results;
- PR URL and current CI/merge state;
- explicit live state: `not deployed` unless separately and actually verified;
- any next action requiring human approval.

Do not claim completion based on a plan, unexecuted tests, a local-only commit, or an unverified deployment.