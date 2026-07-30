#!/usr/bin/env python3
"""Launch, run, and report bounded autonomous repository maintenance."""

from __future__ import annotations

import datetime as dt
import fcntl
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

DEFAULT_STATE_ROOT = Path("/home/debian/.hermes/state/daily-repository-maintenance")
DEFAULT_REPOSITORY = Path("/home/debian/OrchestrationOasis")
DEFAULT_PROMPT = DEFAULT_REPOSITORY / "automation/prompts/daily-repository-maintenance.md"
DEFAULT_HERMES = Path("/home/debian/.local/bin/hermes")
DEFAULT_WORKER = Path("/home/debian/.hermes/scripts/daily_repository_maintenance_worker.py")
MAX_RESULT_BYTES = 40_000
WORKER_TIMEOUT_SECONDS = 50 * 60


@dataclass(frozen=True)
class Paths:
    state_root: Path
    repository: Path
    prompt: Path
    hermes: Path
    worker: Path


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""


def paths_from_env(env: Mapping[str, str] | None = None) -> Paths:
    values = env or os.environ
    return Paths(
        state_root=Path(values.get("DAILY_MAINTENANCE_STATE_ROOT", DEFAULT_STATE_ROOT)),
        repository=Path(values.get("DAILY_MAINTENANCE_REPOSITORY", DEFAULT_REPOSITORY)),
        prompt=Path(values.get("DAILY_MAINTENANCE_PROMPT", DEFAULT_PROMPT)),
        hermes=Path(values.get("DAILY_MAINTENANCE_HERMES", DEFAULT_HERMES)),
        worker=Path(values.get("DAILY_MAINTENANCE_WORKER", DEFAULT_WORKER)),
    )


def local_day(now: dt.datetime | None = None) -> str:
    current = now or dt.datetime.now().astimezone()
    return current.date().isoformat()


def state_paths(paths: Paths, day: str) -> dict[str, Path]:
    return {
        "running": paths.state_root / f"{day}.running",
        "result": paths.state_root / f"{day}.result",
        "delivered": paths.state_root / f"{day}.delivered",
        "lock": paths.state_root / "worker.lock",
    }


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            if content and not content.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    try:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(124)
    except OSError:
        return CommandResult(127)
    return CommandResult(result.returncode, result.stdout[:MAX_RESULT_BYTES])


def repository_preflight(paths: Paths) -> str | None:
    branch = run_command(
        ["git", "branch", "--show-current"], cwd=paths.repository, timeout=15
    )
    status = run_command(
        ["git", "status", "--porcelain"], cwd=paths.repository, timeout=15
    )
    if branch.returncode != 0 or status.returncode != 0:
        return "dépôt Git non vérifiable"
    if branch.stdout.strip() != "main":
        return f"branche active inattendue ({branch.stdout.strip() or 'détachée'})"
    if status.stdout.strip():
        return "arbre Git non propre"
    if not paths.prompt.is_file() or not paths.hermes.is_file():
        return "prompt versionné ou binaire Hermes absent"
    return None


def launch(
    *,
    paths: Paths | None = None,
    now: dt.datetime | None = None,
) -> str:
    paths = paths or paths_from_env()
    day = local_day(now)
    state = state_paths(paths, day)
    paths.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.state_root, 0o700)
    if state["result"].exists() or state["running"].exists():
        return ""

    blocker = repository_preflight(paths)
    if blocker:
        atomic_write(
            state["result"],
            f"⚠️ Maintenance quotidienne non démarrée : {blocker}. Aucun changement effectué.",
        )
        return ""

    unit = f"infraforge-daily-maintenance-{day.replace('-', '')}"
    result = run_command(
        [
            "/usr/bin/systemd-run",
            "--user",
            f"--unit={unit}",
            "--collect",
            "--property=RuntimeMaxSec=55min",
            "--description=Infraforge daily repository maintenance",
            str(paths.worker),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        atomic_write(
            state["result"],
            f"⚠️ Maintenance quotidienne non démarrée : lancement systemd impossible (exit={result.returncode}).",
        )
    return ""


def worker_environment(paths: Paths) -> dict[str, str]:
    env = dict(os.environ)
    venv_bin = paths.repository / ".venv/bin"
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '/usr/bin:/bin')}"
    return env


def normalize_hermes_report(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("session_id:"):
        lines.pop(0)
    return "\n".join(lines).strip()[-MAX_RESULT_BYTES:]


def run_worker(
    *,
    paths: Paths | None = None,
    now: dt.datetime | None = None,
) -> int:
    paths = paths or paths_from_env()
    day = local_day(now)
    state = state_paths(paths, day)
    paths.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.state_root, 0o700)

    lock_stream = state["lock"].open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        if state["result"].exists():
            return 0
        blocker = repository_preflight(paths)
        if blocker:
            atomic_write(
                state["result"],
                f"⚠️ Maintenance quotidienne interrompue avant analyse : {blocker}. Aucun changement effectué.",
            )
            return 1

        atomic_write(state["running"], dt.datetime.now(dt.timezone.utc).isoformat())
        prompt = paths.prompt.read_text(encoding="utf-8")
        command = [
            str(paths.hermes),
            "-s",
            "software-engineering-workflows",
            "-s",
            "github-workflows",
            "chat",
            "-Q",
            "-t",
            "terminal,file,skills,todo",
            "--source",
            "daily-repository-maintenance",
            "-q",
            prompt,
        ]
        result = run_command(
            command,
            cwd=paths.repository,
            timeout=WORKER_TIMEOUT_SECONDS,
            env=worker_environment(paths),
        )
        normalized = normalize_hermes_report(result.stdout)
        if result.returncode == 0 and normalized:
            report = normalized
            exit_code = 0
        elif result.returncode == 124:
            report = (
                "⚠️ Maintenance quotidienne arrêtée après 50 minutes. "
                "Vérifier le dépôt et toute PR daily/* avant le prochain run."
            )
            exit_code = 1
        else:
            report = (
                "⚠️ Maintenance quotidienne terminée sans rapport exploitable "
                f"(exit={result.returncode}). Vérification manuelle requise."
            )
            exit_code = 1
        atomic_write(state["result"], report)
        return exit_code
    finally:
        state["running"].unlink(missing_ok=True)
        lock_stream.close()


def report(
    *,
    paths: Paths | None = None,
    now: dt.datetime | None = None,
) -> str:
    paths = paths or paths_from_env()
    day = local_day(now)
    state = state_paths(paths, day)
    if state["delivered"].exists():
        return ""
    if state["result"].is_file():
        text = state["result"].read_text(encoding="utf-8", errors="replace")
        atomic_write(state["delivered"], dt.datetime.now(dt.timezone.utc).isoformat())
        return text[:MAX_RESULT_BYTES].strip()
    if state["running"].is_file():
        age = time.time() - state["running"].stat().st_mtime
        if age < 65 * 60:
            return ""
        return (
            "⚠️ La maintenance quotidienne dépasse 65 minutes sans résultat. "
            "Le worker est borné par systemd ; vérifier son état et le dépôt."
        )
    return "⚠️ Aucun résultat de maintenance quotidienne n'a été produit aujourd'hui."


def main() -> int:
    name = Path(sys.argv[0]).name
    if "launcher" in name:
        message = launch()
        exit_code = 0
    elif "worker" in name:
        return run_worker()
    elif "reporter" in name:
        message = report()
        exit_code = 0
    else:
        raise SystemExit(
            "invoke as daily_repository_maintenance_launcher.py, "
            "daily_repository_maintenance_worker.py, or "
            "daily_repository_maintenance_reporter.py"
        )
    if message:
        print(message)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
