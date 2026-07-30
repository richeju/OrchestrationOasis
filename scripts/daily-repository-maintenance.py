#!/usr/bin/env python3
"""Isolated daily maintenance candidate generator and deterministic PR gate."""

from __future__ import annotations

import collections
import datetime as dt
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:  # Fail closed in profile_isolation_preflight().
    yaml = None

PARIS = ZoneInfo("Europe/Paris")
DEFAULT_STATE_ROOT = Path("/home/debian/.hermes/state/daily-repository-maintenance")
DEFAULT_WORKTREE_ROOT = Path("/dev/shm/infraforge-daily-maintenance")
DEFAULT_REPOSITORY = Path("/home/debian/OrchestrationOasis")
DEFAULT_PROMPT = DEFAULT_REPOSITORY / "automation/prompts/daily-repository-maintenance.md"
DEFAULT_HERMES = Path("/home/debian/.local/bin/hermes")
DEFAULT_WORKER = Path("/home/debian/.hermes/scripts/daily_repository_maintenance_worker.py")
DEFAULT_PROFILE_HOME = Path("/home/debian/.hermes/profiles/dailymaintainer")
DEFAULT_DOCKER_WRAPPER = Path("/home/debian/.hermes/bin/daily-maintenance/docker")
DOCKER_WRAPPER_CONTENT = '#!/bin/sh\nexec /usr/bin/sudo -n /usr/bin/docker "$@"\n'
HERMES_PROFILE = "dailymaintainer"
HERMES_PROVIDER = "openai-codex"
HERMES_MODEL = "gpt-5.6-sol"
HERMES_DOCKER_IMAGE = (
    "nikolaik/python-nodejs:python3.11-nodejs20@"
    "sha256:8f958bdc1b4a422bfafd97cab4f69836401f616ae985d4b57a53d254f5bcb038"
)
WORKER_TIMEOUT_SECONDS = 50 * 60
MAX_COMMAND_OUTPUT = 200_000
MAX_DIFF_BYTES = 80_000
MAX_DIFF_LINES = 800
MAX_CHANGED_FILES = 3
EXPECTED_ORIGIN = "https://github.com/richeju/OrchestrationOasis.git"

ALLOWED_EXISTING_PATHS = (
    re.compile(r"^docs/[A-Za-z0-9._/-]+\.md$"),
    re.compile(r"^scripts/tests/[A-Za-z0-9._/-]+\.(?:py|sh)$"),
    re.compile(r"^scripts/daily-security-audit\.py$"),
)
FORBIDDEN_PATH_PARTS = (
    ".github/",
    "ansible/",
    "automation/",
    "inventory",
    "deploy",
    "maintenance",
    "patching",
    "reboot",
    "restic",
    "safety",
    "require-ansible-targets",
)
SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"https?://[^\s/:]+:[^\s/@]+@"),
    re.compile(r"(?i)(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[^\s$<{]{8,}"),
    re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/-]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)
KNOWN_JOURNAL_UNITS = {
    "caddy": "caddy",
    "docker": "docker",
    "fail2ban": "fail2ban",
    "hermes": "hermes",
    "kernel": "kernel",
    "openvpn": "openvpn",
    "ssh": "ssh",
    "systemd": "systemd",
}
MESSAGE_CATEGORIES = {
    "authentication_failure": ("authentication failure", "failed password", "invalid user"),
    "connection_failure": ("connection refused", "connection reset", "network is unreachable"),
    "disk_pressure": ("no space left", "read-only file system", "disk quota"),
    "oom": ("out of memory", "oom-kill", "killed process"),
    "permission_denied": ("permission denied", "operation not permitted"),
    "rate_limit": ("rate limit", "too many requests"),
    "segfault": ("segfault", "segmentation fault"),
    "timeout": ("timed out", "timeout"),
    "tls_failure": ("certificate verify failed", "tls handshake", "ssl error"),
    "unhealthy": ("unhealthy", "health check failed"),
}


@dataclass(frozen=True)
class Paths:
    state_root: Path
    worktree_root: Path
    repository: Path
    prompt: Path
    hermes: Path
    worker: Path
    profile_home: Path
    docker_wrapper: Path


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""


def paths_from_env(env: Mapping[str, str] | None = None) -> Paths:
    values = env or os.environ
    return Paths(
        Path(values.get("DAILY_MAINTENANCE_STATE_ROOT", DEFAULT_STATE_ROOT)),
        Path(values.get("DAILY_MAINTENANCE_WORKTREE_ROOT", DEFAULT_WORKTREE_ROOT)),
        Path(values.get("DAILY_MAINTENANCE_REPOSITORY", DEFAULT_REPOSITORY)),
        Path(values.get("DAILY_MAINTENANCE_PROMPT", DEFAULT_PROMPT)),
        Path(values.get("DAILY_MAINTENANCE_HERMES", DEFAULT_HERMES)),
        Path(values.get("DAILY_MAINTENANCE_WORKER", DEFAULT_WORKER)),
        Path(values.get("DAILY_MAINTENANCE_PROFILE_HOME", DEFAULT_PROFILE_HOME)),
        Path(values.get("DAILY_MAINTENANCE_DOCKER_WRAPPER", DEFAULT_DOCKER_WRAPPER)),
    )


def local_day(now: dt.datetime | None = None) -> str:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    return current.astimezone(PARIS).date().isoformat()


def state_paths(paths: Paths, day: str) -> dict[str, Path]:
    return {
        "launching": paths.state_root / f"{day}.launching",
        "running": paths.state_root / f"{day}.running",
        "result": paths.state_root / f"{day}.result",
        "reported": paths.state_root / f"{day}.reported",
        "lock": paths.state_root / "state.lock",
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
        Path(temporary).unlink(missing_ok=True)


def state_lock(paths: Paths):
    paths.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.state_root, 0o700)
    stream = (paths.state_root / "state.lock").open("a+", encoding="utf-8")
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    return stream


def repository_lock(paths: Paths):
    paths.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stream = (paths.state_root / "repository.lock").open("a+", encoding="utf-8")
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    return stream


def git_argv(*args: str) -> list[str]:
    """Disable hooks and signing for every host Git mutation."""
    return [
        "git", "-c", "core.hooksPath=/dev/null",
        "-c", "core.attributesFile=/dev/null",
        "-c", "commit.gpgSign=false", "-c", "push.gpgSign=false",
        *args,
    ]


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    try:
        process = subprocess.Popen(
            list(argv), cwd=cwd, env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError:
        return CommandResult(127)

    output = bytearray()

    def drain() -> None:
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            remaining = MAX_COMMAND_OUTPUT - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
        returncode = 124
    else:
        # Do not permit a completed command to leave descendants holding pipes.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    reader.join(timeout=5)
    if reader.is_alive():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        reader.join(timeout=2)
    if process.stdout is not None:
        process.stdout.close()
    if timed_out:
        returncode = 124
    return CommandResult(returncode, bytes(output).decode("utf-8", errors="replace"))


def run_quiet_process(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout: int
) -> int:
    try:
        process = subprocess.Popen(
            list(argv), cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return 127
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=20)
            return 124
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            return 124


def repository_preflight(paths: Paths) -> str | None:
    branch = run_command(git_argv("branch", "--show-current"), cwd=paths.repository)
    status = run_command(git_argv("status", "--porcelain"), cwd=paths.repository)
    origin = run_command(git_argv("remote", "get-url", "origin"), cwd=paths.repository)
    push_origin = run_command(git_argv("remote", "get-url", "--push", "origin"), cwd=paths.repository)
    if branch.returncode != 0 or status.returncode != 0 or origin.returncode != 0 or push_origin.returncode != 0:
        return "dépôt Git non vérifiable"
    if branch.stdout.strip() != "main":
        return "branche canonique inattendue"
    if status.stdout.strip():
        return "checkout canonique non propre"
    if origin.stdout.strip() != EXPECTED_ORIGIN or push_origin.stdout.strip() != EXPECTED_ORIGIN:
        return "remote Git canonique inattendu"
    if not paths.prompt.is_file() or not os.access(paths.hermes, os.X_OK):
        return "prompt versionné ou binaire Hermes absent"
    if paths.docker_wrapper.is_symlink() or not paths.docker_wrapper.is_file():
        return "wrapper Docker isolé absent"
    try:
        wrapper_stat = paths.docker_wrapper.stat()
        wrapper_parent_stat = paths.docker_wrapper.parent.stat()
        if paths.docker_wrapper.read_text(encoding="utf-8") != DOCKER_WRAPPER_CONTENT:
            return "wrapper Docker isolé invalide"
    except OSError:
        return "wrapper Docker isolé non vérifiable"
    if (
        wrapper_stat.st_uid != os.getuid() or (wrapper_stat.st_mode & 0o777) != 0o700
        or wrapper_parent_stat.st_uid != os.getuid() or (wrapper_parent_stat.st_mode & 0o777) != 0o700
    ):
        return "permissions du wrapper Docker isolé invalides"
    profile_error = profile_isolation_preflight(paths)
    if profile_error:
        return profile_error
    return None


def profile_isolation_preflight(paths: Paths) -> str | None:
    if yaml is None:
        return "parseur YAML indisponible pour valider le profil isolé"
    if not paths.profile_home.is_dir():
        return "profil Hermes isolé absent"
    config_path = paths.profile_home / "config.yaml"
    config: dict[str, Any] = {}
    if config_path.exists():
        if config_path.is_symlink() or not config_path.is_file():
            return "configuration du profil isolé invalide"
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError, yaml.YAMLError):
            return "configuration du profil isolé invalide"
        if not isinstance(loaded, dict):
            return "configuration du profil isolé invalide"
        config = loaded
    if "terminal" in config:
        return "section terminal interdite dans le profil isolé"
    skills: dict[str, Any] = {}

    if isinstance(config.get("skills"), dict):
        skills = config["skills"]

    if skills.get("external_dirs") not in (None, []):
        return "external skills interdits dans le profil isolé"


    auto_mounted_roots = (
        "skills", "plugins", "cache/documents", "cache/images", "cache/audio",
        "cache/videos", "cache/screenshots", "cache/web", "cache/delegation",
        "document_cache", "image_cache", "audio_cache", "video_cache",
        "browser_screenshots", "web_cache", "delegation_cache",
    )
    for relative in auto_mounted_roots:
        root = paths.profile_home / relative
        if not root.exists():
            continue
        if root.is_symlink() or root.is_file():
            return "contenu auto-monté interdit dans le profil isolé"
        try:
            if any(entry.is_file() or entry.is_symlink() for entry in root.rglob("*")):
                return "contenu auto-monté interdit dans le profil isolé"
        except OSError:
            return "contenu du profil isolé non vérifiable"
    return None


def launch(*, paths: Paths | None = None, now: dt.datetime | None = None) -> str:
    paths = paths or paths_from_env()
    day = local_day(now)
    state = state_paths(paths, day)
    lock = state_lock(paths)
    try:
        if state["result"].exists() or state["reported"].exists() or state["running"].exists() or state["launching"].exists():
            return ""
        blocker = repository_preflight(paths)
        if blocker:
            atomic_write(state["result"], f"⚠️ Maintenance quotidienne non démarrée : {blocker}.")
            return ""
        atomic_write(state["launching"], dt.datetime.now(dt.timezone.utc).isoformat())
        unit = f"infraforge-daily-maintenance-{day.replace('-', '')}"
        result = run_command([
            "/usr/bin/systemd-run", "--user", f"--unit={unit}", "--collect",
            "--property=RuntimeMaxSec=55min", "--property=TimeoutStopSec=30s",
            "--property=KillMode=control-group", "--property=MemoryMax=3G",
            "--property=CPUQuota=200%", "--property=TasksMax=384", "--description=Isolated daily repository maintenance",
            str(paths.worker),
        ])
        if result.returncode != 0:
            atomic_write(state["result"], f"⚠️ Maintenance quotidienne non démarrée : lancement systemd impossible (exit={result.returncode}).")
            state["launching"].unlink(missing_ok=True)
        return ""
    finally:
        lock.close()


def classify_unit(unit: str) -> str:
    lowered = unit.lower()
    for needle, known in KNOWN_JOURNAL_UNITS.items():
        if needle in lowered:
            return known
    return "other"


def classify_message(message: str) -> str:
    lowered = message.lower()
    for category, needles in MESSAGE_CATEGORIES.items():
        if any(needle in lowered for needle in needles):
            return category
    return "other_warning"


def collect_journal(*, user: bool = False) -> dict[str, int]:
    argv = ["journalctl"]
    if user:
        argv += ["--user", "-u", "hermes-gateway.service"]
    argv += ["--since", "24 hours ago", "-p", "warning..alert", "--no-pager", "-o", "json", "-n", "500"]
    result = run_command(argv, timeout=30)
    counts: collections.Counter[str] = collections.Counter()
    if result.returncode != 0:
        return {"collection_error": 1}
    for line in result.stdout.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        unit = classify_unit(str(record.get("_SYSTEMD_UNIT") or record.get("SYSLOG_IDENTIFIER") or "other"))
        category = classify_message(str(record.get("MESSAGE") or ""))
        priority = str(record.get("PRIORITY") or "unknown")
        if priority not in {"0", "1", "2", "3", "4"}:
            priority = "unknown"
        counts[f"{unit}:{category}:p{priority}"] += 1
    return dict(sorted(counts.items()))


def collect_evidence(paths: Paths) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "window_hours": 24,
        "journal_categories": collect_journal(),
        "hermes_journal_categories": collect_journal(user=True),
    }
    docker = run_command(["/usr/bin/sudo", "-n", "/usr/bin/docker", "ps", "-a", "--format", "{{.State}}|{{.Status}}"], timeout=30)
    states: collections.Counter[str] = collections.Counter()
    if docker.returncode == 0:
        for line in docker.stdout.splitlines():
            lowered = line.lower()
            if "unhealthy" in lowered:
                states["unhealthy"] += 1
            elif "health: starting" in lowered:
                states["starting"] += 1
            elif lowered.startswith("running|") or lowered.startswith("up|"):
                states["running"] += 1
            elif "restarting" in lowered:
                states["restarting"] += 1
            else:
                states["not_running"] += 1
    else:
        states["collection_error"] += 1
    evidence["docker_states"] = dict(sorted(states.items()))

    runs = run_command(["gh", "run", "list", "--limit", "20", "--json", "workflowName,status,conclusion"], cwd=paths.repository, timeout=30)
    workflow_counts: collections.Counter[str] = collections.Counter()
    if runs.returncode == 0:
        try:
            for run in json.loads(runs.stdout):
                workflow = str(run.get("workflowName") or "other")
                if workflow not in {"CI", "Maintenance", "Deploy"}:
                    workflow = "other"
                status = str(run.get("status") or "unknown")
                conclusion = str(run.get("conclusion") or "none")
                if status not in {"completed", "pending", "queued", "in_progress", "waiting", "requested"}:
                    status = "other"
                if conclusion not in {"success", "failure", "cancelled", "skipped", "timed_out", "none", ""}:
                    conclusion = "other"
                workflow_counts[f"{workflow}:{status}:{conclusion or 'none'}"] += 1
        except (TypeError, ValueError):
            workflow_counts["collection_error"] += 1
    else:
        workflow_counts["collection_error"] += 1
    evidence["github_workflow_states"] = dict(sorted(workflow_counts.items()))

    issues = run_command(["gh", "issue", "list", "--state", "open", "--limit", "100", "--json", "number"], cwd=paths.repository, timeout=30)
    try:
        evidence["open_issue_count"] = len(json.loads(issues.stdout)) if issues.returncode == 0 else -1
    except (TypeError, ValueError):
        evidence["open_issue_count"] = -1
    return evidence


def open_daily_pr(paths: Paths) -> tuple[dict[str, str] | None, str | None]:
    result = run_command(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", "number,url,headRefName"], cwd=paths.repository, timeout=30)
    if result.returncode != 0:
        return None, "état des PR GitHub non vérifiable"
    try:
        for pr in json.loads(result.stdout):
            head = str(pr.get("headRefName") or "")
            url = str(pr.get("url") or "")
            if head.startswith("daily/") and re.fullmatch(r"https://github\.com/richeju/OrchestrationOasis/pull/\d+", url):
                return {"number": str(int(pr["number"])), "url": url}, None
    except (KeyError, TypeError, ValueError):
        return None, "réponse GitHub invalide"
    return None, None


def prepare_worktree(paths: Paths, day: str) -> tuple[Path | None, str | None, str | None]:
    prune = run_command(git_argv("worktree", "prune"), cwd=paths.repository, timeout=30)
    if prune.returncode != 0:
        return None, None, "nettoyage des métadonnées de worktree impossible"
    fetch = run_command(git_argv("fetch", "--prune", "origin", "main"), cwd=paths.repository, timeout=90)
    if fetch.returncode != 0:
        return None, None, "fetch origin/main impossible"
    resolved = run_command(git_argv("rev-parse", "--verify", "origin/main^{commit}"), cwd=paths.repository)
    base_sha = resolved.stdout.strip()
    if resolved.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        return None, None, "SHA origin/main non vérifiable"
    head = run_command(git_argv("rev-parse", "--verify", "HEAD^{commit}"), cwd=paths.repository)
    if head.returncode != 0 or head.stdout.strip() != base_sha:
        return None, None, "checkout canonique non aligné avec origin/main"
    path = paths.worktree_root / day
    branch = f"daily/{day}-maintenance"
    if path.exists():
        return None, None, "worktree quotidien déjà présent"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    result = run_command(git_argv("worktree", "add", "-b", branch, str(path), base_sha), cwd=paths.repository, timeout=60)
    if result.returncode != 0:
        return None, None, "création du worktree isolé impossible"
    return path, base_sha, None


def sandbox_environment(paths: Paths, worktree: Path, evidence_file: Path) -> dict[str, str]:
    env = {
        "HOME": os.environ.get("HOME", "/home/debian"),
        "USER": os.environ.get("USER", "debian"),
        "LOGNAME": os.environ.get("LOGNAME", "debian"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PATH": f"{paths.docker_wrapper.parent}:/home/debian/.local/bin:/usr/local/bin:/usr/bin:/bin",
        "TERMINAL_ENV": "docker",
        "TERMINAL_CWD": "/workspace",
        "TERMINAL_DOCKER_NETWORK": "false",
        "TERMINAL_DOCKER_IMAGE": HERMES_DOCKER_IMAGE,
        "TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES": "false",
        "TERMINAL_DOCKER_ORPHAN_REAPER": "true",
        "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE": "false",
        "TERMINAL_DOCKER_FORWARD_ENV": "[]",
        "TERMINAL_DOCKER_ENV": "{}",
        "TERMINAL_DOCKER_EXTRA_ARGS": json.dumps([
            "--read-only", "--tmpfs", "/root:rw,noexec,nosuid,size=128m",
        ]),
        "TERMINAL_DOCKER_RUN_AS_HOST_USER": "false",
        "TERMINAL_CONTAINER_PERSISTENT": "false",
        "TERMINAL_CONTAINER_CPU": "2",
        "TERMINAL_CONTAINER_MEMORY": "2048",
        "TERMINAL_TIMEOUT": "120",
        "TERMINAL_DOCKER_VOLUMES": json.dumps([
            f"{worktree}:/workspace",
            f"{worktree / '.git'}:/workspace/.git:ro",
            f"{evidence_file}:/workspace/.daily-evidence.json:ro",
        ]),
    }
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def hermes_worker_command(paths: Paths) -> list[str]:
    return [
        str(paths.hermes), "-p", HERMES_PROFILE,
        "--ignore-rules", "-m", HERMES_MODEL, "--provider", HERMES_PROVIDER,
        "chat", "-Q", "-t", "terminal",
        "--source", "daily-repository-maintenance",
        "-q", paths.prompt.read_text(encoding="utf-8"),
    ]


def profile_container_ids() -> list[str] | None:
    result = run_command(
        ["sudo", "-n", "/usr/bin/docker", "ps", "-aq", "--filter", "label=hermes-agent=1", "--filter", f"label=hermes-profile={HERMES_PROFILE}"],
        timeout=20,
    )
    if result.returncode != 0:
        return None
    identifiers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if any(not re.fullmatch(r"[0-9a-f]{12,64}", identifier) for identifier in identifiers):
        return None
    return identifiers


def cleanup_profile_containers() -> bool:
    """Synchronously remove every container owned by the dedicated profile."""
    for _ in range(4):
        identifiers = profile_container_ids()
        if identifiers is None:
            return False
        if not identifiers:
            return True
        run_command(
            ["sudo", "-n", "/usr/bin/docker", "rm", "-f", *identifiers],
            timeout=30,
        )
        time.sleep(0.2)
    return profile_container_ids() == []


def changed_paths(worktree: Path, base_sha: str) -> list[str]:
    tracked = run_command(git_argv("diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", base_sha), cwd=worktree)
    untracked = run_command(git_argv("ls-files", "--others", "--exclude-standard", "-z"), cwd=worktree)
    if tracked.returncode != 0 or untracked.returncode != 0:
        return ["<git-error>"]
    return sorted({part for part in (tracked.stdout + untracked.stdout).split("\0") if part and part != ".daily-evidence.json"})


def validate_diff(worktree: Path, base_sha: str, paths: list[str]) -> str | None:
    if not paths:
        return None
    if len(paths) > MAX_CHANGED_FILES:
        return "trop de fichiers modifiés"
    if "scripts/daily-security-audit.py" in paths and not any(
        relative.startswith("scripts/tests/") for relative in paths
    ):
        return "modification du contrôleur sans test de régression"
    for relative in paths:
        if relative == "<git-error>" or relative.startswith("/") or ".." in Path(relative).parts:
            return "chemin de diff invalide"
        lowered = relative.lower()
        if any(part in lowered for part in FORBIDDEN_PATH_PARTS):
            return "chemin interdit"
        if not any(pattern.fullmatch(relative) for pattern in ALLOWED_EXISTING_PATHS):
            return "chemin hors allowlist"
        if run_command(git_argv("cat-file", "-e", f"{base_sha}:{relative}"), cwd=worktree).returncode != 0:
            return "nouveau fichier non autorisé"
        candidate = worktree / relative
        if candidate.is_symlink() or not candidate.is_file():
            return "type de fichier interdit"
    summary = run_command(git_argv("diff", "--no-ext-diff", "--no-textconv", "--summary", base_sha), cwd=worktree, timeout=30)
    if summary.returncode != 0 or summary.stdout.strip():
        return "changement de type, mode ou renommage interdit"
    diff = run_command(git_argv("diff", "--no-ext-diff", "--no-textconv", "--binary", base_sha), cwd=worktree, timeout=30)
    if diff.returncode != 0:
        return "diff non lisible"
    encoded = diff.stdout.encode("utf-8", errors="replace")
    if len(encoded) > MAX_DIFF_BYTES or diff.stdout.count("\n") > MAX_DIFF_LINES:
        return "diff trop volumineux"
    if "GIT binary patch" in diff.stdout or "\x00" in diff.stdout:
        return "contenu binaire interdit"
    if any(pattern.search(diff.stdout) for pattern in SECRET_PATTERNS):
        return "secret potentiel détecté dans le diff"
    return None


def cleanup_worktree(paths: Paths, worktree: Path, branch: str) -> bool:
    removed = run_command(git_argv("worktree", "remove", "--force", str(worktree)), cwd=paths.repository, timeout=60)
    deleted = run_command(git_argv("branch", "-D", branch), cwd=paths.repository, timeout=30)
    return removed.returncode == 0 and deleted.returncode == 0


def static_host_validation(worktree: Path, base_sha: str) -> tuple[bool, str]:
    """Validate without executing any model-modified repository content."""
    check = run_command(git_argv("diff", "--no-ext-diff", "--no-textconv", "--check", base_sha), cwd=worktree, timeout=30)
    if check.returncode != 0:
        return False, "git diff --check"
    return True, "static policy"


def stage_without_filters(worktree: Path, base_sha: str, files: list[str]) -> str | None:
    for relative in files:
        tree = run_command(git_argv("ls-tree", base_sha, "--", relative), cwd=worktree)
        match = re.fullmatch(r"(100644|100755) blob [0-9a-f]{40}\t.+\n?", tree.stdout)
        if tree.returncode != 0 or not match:
            return "mode Git de base non vérifiable"
        blob = run_command(git_argv("hash-object", "-w", "--no-filters", "--", relative), cwd=worktree)
        object_id = blob.stdout.strip()
        if blob.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", object_id):
            return "création du blob Git impossible"
        staged = run_command(
            git_argv("update-index", "--add", "--cacheinfo", f"{match.group(1)},{object_id},{relative}"),
            cwd=worktree,
        )
        if staged.returncode != 0:
            return "indexation Git déterministe impossible"
    return None


def create_commit_without_hooks(worktree: Path, base_sha: str, branch: str, message: str) -> tuple[str | None, str | None]:
    tree = run_command(git_argv("write-tree"), cwd=worktree)
    tree_id = tree.stdout.strip()
    if tree.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", tree_id):
        return None, "création du tree Git impossible"
    commit = run_command(git_argv("commit-tree", tree_id, "-p", base_sha, "-m", message), cwd=worktree)
    commit_id = commit.stdout.strip()
    if commit.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit_id):
        return None, "création du commit Git impossible"
    updated = run_command(
        git_argv("update-ref", f"refs/heads/{branch}", commit_id, base_sha), cwd=worktree
    )
    if updated.returncode != 0:
        return None, "mise à jour déterministe de la branche impossible"
    return commit_id, None


def base_is_unchanged(paths: Paths, base_sha: str) -> bool:
    fetched = run_command(git_argv("fetch", "--no-tags", "origin", "main"), cwd=paths.repository, timeout=120)
    if fetched.returncode != 0:
        return False
    resolved = run_command(git_argv("rev-parse", "--verify", "origin/main^{commit}"), cwd=paths.repository)
    head = run_command(git_argv("rev-parse", "--verify", "HEAD^{commit}"), cwd=paths.repository)
    return (
        resolved.returncode == 0 and resolved.stdout.strip() == base_sha
        and head.returncode == 0 and head.stdout.strip() == base_sha
        and repository_preflight(paths) is None
    )


def published_pr_for_branch(paths: Paths, branch: str) -> tuple[str | None, str | None]:
    result = run_command([
        "gh", "pr", "list", "--state", "open", "--head", branch,
        "--limit", "1", "--json", "url",
    ], cwd=paths.repository, timeout=30)
    if result.returncode != 0:
        return None, "état GitHub non vérifiable après création de PR"
    try:
        rows = json.loads(result.stdout)
        url = str(rows[0]["url"]) if len(rows) == 1 else ""
    except (KeyError, TypeError, ValueError):
        return None, "réponse GitHub invalide après création de PR"
    if not rows:
        return None, None
    if re.fullmatch(r"https://github\.com/richeju/OrchestrationOasis/pull/\d+", url):
        return url, None
    return None, "URL de PR GitHub invalide"


def remote_branch_state(worktree: Path, branch: str) -> tuple[str | None, str | None]:
    result = run_command(
        git_argv("ls-remote", "--heads", "origin", f"refs/heads/{branch}"),
        cwd=worktree, timeout=60,
    )
    if result.returncode != 0:
        return None, "état de branche distante non vérifiable"
    if not result.stdout.strip():
        return None, None
    match = re.fullmatch(r"([0-9a-f]{40})\trefs/heads/[^\s]+\n?", result.stdout)
    if not match:
        return None, "réponse de branche distante invalide"
    return match.group(1), None


def publish_pr(paths: Paths, worktree: Path, base_sha: str, day: str, files: list[str]) -> tuple[str | None, str | None]:
    branch = f"daily/{day}-maintenance"
    staging_error = stage_without_filters(worktree, base_sha, files)
    if staging_error:
        return None, staging_error
    commit_id, commit_error = create_commit_without_hooks(
        worktree, base_sha, branch, f"chore: daily maintenance candidate {day}"
    )
    if commit_error or not commit_id:
        return None, commit_error or "identifiant du commit déterministe absent"
    push = run_command(
        git_argv("push", "--no-verify", "-u", "origin", f"{commit_id}:refs/heads/{branch}"),
        cwd=worktree,
        timeout=120,
    )
    if push.returncode != 0:
        remote_commit, remote_error = remote_branch_state(worktree, branch)
        if remote_error:
            return None, f"push non confirmé ; {remote_error} ; aucune suppression distante"
        if remote_commit == commit_id:
            return None, "push non confirmé ; commit présent sur branche distante conservée"
        if remote_commit:
            return None, "push refusé ; branche distante préexistante préservée"
        return None, "push impossible"
    body = (
        "## Daily maintenance candidate\n\n"
        "Generated in an air-gapped Docker sandbox from aggregate evidence only.\n\n"
        "- No automatic merge\n"
        "- Canonical checkout untouched\n"
        "- Deterministic path/diff/secret policy: passed\n"
        "- `git diff --check`: passed\n"
        "- Candidate code was not executed on the VPS\n"
        "- GitHub-hosted CI remains mandatory before human review\n"
        f"- Changed existing allowlisted files: {len(files)}\n"
    )
    pr = run_command([
        "gh", "pr", "create", "--base", "main", "--head", branch,
        "--title", f"chore: daily maintenance candidate {day}", "--body", body,
    ], cwd=worktree, timeout=60)
    url = pr.stdout.strip().splitlines()[-1] if pr.returncode == 0 and pr.stdout.strip() else ""
    if not re.fullmatch(r"https://github\.com/richeju/OrchestrationOasis/pull/\d+", url):
        recovered, lookup_error = published_pr_for_branch(paths, branch)
        if recovered:
            return recovered, None
        if lookup_error:
            return None, f"création de PR non confirmée ; {lookup_error} ; branche distante conservée"
        return None, "création de PR non confirmée ; branche distante conservée pour éviter toute suppression destructive"
    return url, None


def run_worker(*, paths: Paths | None = None, now: dt.datetime | None = None) -> int:
    paths = paths or paths_from_env()
    day = local_day(now)
    state = state_paths(paths, day)
    lock = state_lock(paths)
    try:
        if state["result"].exists() or state["reported"].exists() or state["running"].exists():
            return 0
        state["launching"].unlink(missing_ok=True)
        blocker = repository_preflight(paths)
        if blocker:
            atomic_write(state["result"], f"⚠️ Maintenance quotidienne interrompue : {blocker}.")
            return 1
        existing, github_error = open_daily_pr(paths)
        if github_error:
            atomic_write(state["result"], f"⚠️ Maintenance quotidienne interrompue : {github_error}.")
            return 1
        if existing:
            atomic_write(state["result"], f"ℹ️ Maintenance quotidienne : aucune nouvelle tâche. La PR daily existante reste à examiner : {existing['url']}")
            return 0
        atomic_write(state["running"], dt.datetime.now(dt.timezone.utc).isoformat())
    finally:
        lock.close()

    repo_guard = repository_lock(paths)
    worktree: Path | None = None
    base_sha: str | None = None
    branch = f"daily/{day}-maintenance"
    try:
        worktree, base_sha, error = prepare_worktree(paths, day)
        if error or worktree is None or base_sha is None:
            atomic_write(state["result"], f"⚠️ Maintenance quotidienne interrompue : {error}.")
            return 1
        evidence = collect_evidence(paths)
        evidence_file = worktree / ".daily-evidence.json"
        atomic_write(evidence_file, json.dumps(evidence, sort_keys=True), mode=0o600)
        if not cleanup_profile_containers():
            evidence_file.unlink(missing_ok=True)
            atomic_write(state["result"], "⚠️ Maintenance quotidienne interrompue : conteneur Hermes antérieur non nettoyé.")
            return 1
        command = hermes_worker_command(paths)
        try:
            code = run_quiet_process(
                command,
                cwd=paths.repository,
                env=sandbox_environment(paths, worktree, evidence_file),
                timeout=WORKER_TIMEOUT_SECONDS,
            )
        finally:
            containers_removed = cleanup_profile_containers()
            evidence_file.unlink(missing_ok=True)
        if not containers_removed:
            atomic_write(state["result"], f"⚠️ Maintenance quotidienne interrompue : teardown Docker non confirmé. Worktree conservé : {worktree}")
            return 1
        if code != 0:
            atomic_write(state["result"], f"⚠️ Maintenance quotidienne : worker isolé en échec (exit={code}). Worktree conservé pour analyse : {worktree}")
            return 1
        files = changed_paths(worktree, base_sha)
        if not files:
            if not cleanup_worktree(paths, worktree, branch):
                atomic_write(state["result"], "⚠️ Aucun changement candidat, mais le nettoyage du worktree a échoué.")
                return 1
            atomic_write(state["result"], "ℹ️ Maintenance quotidienne : aucun bugfix ou improvement sûr et justifié aujourd’hui. Aucun changement créé.")
            return 0
        policy_error = validate_diff(worktree, base_sha, files)
        if policy_error:
            atomic_write(state["result"], f"⚠️ Candidat quotidien rejeté par la politique déterministe : {policy_error}. Worktree conservé : {worktree}")
            return 1
        valid, failed_check = static_host_validation(worktree, base_sha)
        if not valid:
            atomic_write(state["result"], f"⚠️ Candidat quotidien non publié : échec de {failed_check}. Worktree conservé : {worktree}")
            return 1
        if not base_is_unchanged(paths, base_sha):
            atomic_write(state["result"], "⚠️ Candidat quotidien non publié : base Git ou checkout canonique modifié pendant le run. Worktree conservé.")
            return 1
        url, publish_error = publish_pr(paths, worktree, base_sha, day, files)
        if publish_error or not url:
            atomic_write(state["result"], f"⚠️ Candidat validé localement mais non publié : {publish_error}. Worktree conservé : {worktree}")
            return 1
        if not cleanup_worktree(paths, worktree, branch):
            atomic_write(state["result"], f"⚠️ PR publiée mais nettoyage local incomplet : {url}. Aucune fusion ni aucun déploiement automatique.")
            return 1
        atomic_write(state["result"], f"✅ Candidat quotidien publié en PR, sans fusion ni déploiement : {url}. Fichiers allowlistés modifiés : {len(files)}. Politique statique : OK ; tests/scans délégués à la CI GitHub isolée.")
        return 0
    finally:
        repo_guard.close()
        state["running"].unlink(missing_ok=True)


def report(*, paths: Paths | None = None, now: dt.datetime | None = None) -> str:
    paths = paths or paths_from_env()
    state = state_paths(paths, local_day(now))
    lock = state_lock(paths)
    try:
        if state["result"].is_file():
            payload = state["result"].read_text(encoding="utf-8", errors="replace")[:4000].strip()
            os.replace(state["result"], state["reported"])
            return payload
        if state["reported"].exists():
            return ""
        if state["running"].exists():
            atomic_write(state["reported"], "running status emitted")
            return "⚠️ Maintenance quotidienne toujours active après une heure ; le service systemd la bornera automatiquement."
        atomic_write(state["reported"], "missing status emitted")
        return "⚠️ Aucun résultat de maintenance quotidienne n’a été produit aujourd’hui."
    finally:
        lock.close()


def main() -> int:
    name = Path(sys.argv[0]).name
    if "launcher" in name:
        message, code = launch(), 0
    elif "worker" in name:
        return run_worker()
    elif "reporter" in name:
        message, code = report(), 0
    else:
        raise SystemExit("invoke as daily_repository_maintenance_launcher.py, worker.py, or reporter.py")
    if message:
        print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
