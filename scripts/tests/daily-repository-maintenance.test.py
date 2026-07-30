#!/usr/bin/env python3
import datetime as dt
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "daily-repository-maintenance.py"
SPEC = importlib.util.spec_from_file_location("daily_repository_maintenance", SCRIPT)
assert SPEC and SPEC.loader
MAINT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MAINT
SPEC.loader.exec_module(MAINT)

DAY = dt.datetime(2026, 7, 31, 10, 0, tzinfo=dt.timezone.utc)


def test_paths(root: Path):
    repository = root / "repo"
    repository.mkdir()
    prompt = repository / "prompt.md"
    prompt.write_text("Do one safe task.\n", encoding="utf-8")
    hermes = root / "hermes"
    hermes.write_text("#!/bin/sh\n", encoding="utf-8")
    worker = root / "worker.py"
    worker.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return MAINT.Paths(root / "state", repository, prompt, hermes, worker)


class DailyRepositoryMaintenanceTests(unittest.TestCase):
    def test_launch_records_preflight_blocker_without_starting_systemd(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = test_paths(Path(directory))
            with mock.patch.object(
                MAINT, "repository_preflight", return_value="arbre Git non propre"
            ), mock.patch.object(MAINT, "run_command") as runner:
                self.assertEqual(MAINT.launch(paths=paths, now=DAY), "")
            runner.assert_not_called()
            state = MAINT.state_paths(paths, "2026-07-31")
            self.assertIn(
                "arbre Git non propre",
                state["result"].read_text(encoding="utf-8"),
            )
            self.assertEqual(state["result"].stat().st_mode & 0o777, 0o600)

    def test_launch_starts_bounded_user_systemd_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = test_paths(Path(directory))
            with mock.patch.object(
                MAINT, "repository_preflight", return_value=None
            ), mock.patch.object(
                MAINT,
                "run_command",
                return_value=MAINT.CommandResult(0),
            ) as runner:
                self.assertEqual(MAINT.launch(paths=paths, now=DAY), "")
            argv = runner.call_args.args[0]
            self.assertEqual(argv[:2], ["/usr/bin/systemd-run", "--user"])
            self.assertIn("--property=RuntimeMaxSec=55min", argv)
            self.assertEqual(argv[-1], str(paths.worker))

    def test_worker_writes_sanitized_final_report_and_clears_running(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = test_paths(Path(directory))
            with mock.patch.object(
                MAINT, "repository_preflight", return_value=None
            ), mock.patch.object(
                MAINT,
                "run_command",
                return_value=MAINT.CommandResult(0, "✅ Aucun changement sûr aujourd'hui.\n"),
            ):
                self.assertEqual(MAINT.run_worker(paths=paths, now=DAY), 0)
            state = MAINT.state_paths(paths, "2026-07-31")
            self.assertFalse(state["running"].exists())
            self.assertEqual(
                state["result"].read_text(encoding="utf-8").strip(),
                "✅ Aucun changement sûr aujourd'hui.",
            )

    def test_normalize_report_removes_cli_session_metadata(self):
        report = MAINT.normalize_hermes_report(
            "session_id: 20260730_example\n✅ Rapport utile\n"
        )
        self.assertEqual(report, "✅ Rapport utile")

    def test_report_is_delivered_once(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = test_paths(Path(directory))
            state = MAINT.state_paths(paths, "2026-07-31")
            MAINT.atomic_write(state["result"], "résultat quotidien")
            self.assertEqual(MAINT.report(paths=paths, now=DAY), "résultat quotidien")
            self.assertEqual(MAINT.report(paths=paths, now=DAY), "")
            self.assertTrue(state["delivered"].exists())

    def test_report_is_silent_while_recent_worker_is_running(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = test_paths(Path(directory))
            state = MAINT.state_paths(paths, "2026-07-31")
            MAINT.atomic_write(state["running"], "started")
            self.assertEqual(MAINT.report(paths=paths, now=DAY), "")
            old = time.time() - 66 * 60
            os.utime(state["running"], (old, old))
            self.assertIn("dépasse 65 minutes", MAINT.report(paths=paths, now=DAY))


if __name__ == "__main__":
    unittest.main()
