#!/usr/bin/env python3
import datetime as dt
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "weekly-conditional-reboot.py"
SPEC = importlib.util.spec_from_file_location("weekly_conditional_reboot", SCRIPT)
assert SPEC and SPEC.loader
REBOOT = importlib.util.module_from_spec(SPEC)
import sys

sys.modules[SPEC.name] = REBOOT
SPEC.loader.exec_module(REBOOT)


class WeeklyConditionalRebootTests(unittest.TestCase):
    def test_prepare_is_silent_without_reboot_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def runner(*args, **kwargs):
                calls.append((args, kwargs))
                raise AssertionError("runner must not be called")

            message = REBOOT.prepare(
                marker=root / "missing",
                state_path=root / "state.json",
                boot_id_path=root / "boot-id",
                runner=runner,
            )
            self.assertEqual(message, "")
            self.assertEqual(calls, [])

    def test_prepare_schedules_verified_timer_and_persists_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "reboot-required"
            marker.touch()
            boot = root / "boot-id"
            boot.write_text("old-boot\n", encoding="utf-8")
            state = root / "state.json"
            calls = []

            def runner(argv, *, timeout=30, sudo=False):
                calls.append((tuple(argv), sudo))
                if argv[0] == "/usr/bin/systemd-run":
                    return REBOOT.CommandResult(0)
                if len(argv) >= 3 and argv[0] == "/usr/bin/systemctl" and argv[1] == "is-active":
                    return REBOOT.CommandResult(0, "active\n")
                raise AssertionError(argv)

            message = REBOOT.prepare(
                marker=marker,
                state_path=state,
                boot_id_path=boot,
                runner=runner,
                now=dt.datetime(2026, 7, 27, 3, 30, tzinfo=dt.timezone.utc),
            )
            self.assertIn("programmé dans 2 minutes", message)
            saved = __import__("json").loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["boot_id"], "old-boot")
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
            self.assertTrue(any(call[0][0] == "/usr/bin/systemd-run" for call in calls))

    def test_prepare_failure_does_not_persist_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "reboot-required"
            marker.touch()
            boot = root / "boot-id"
            boot.write_text("old-boot\n", encoding="utf-8")
            state = root / "state.json"

            def runner(argv, *, timeout=30, sudo=False):
                return REBOOT.CommandResult(1)

            message = REBOOT.prepare(
                marker=marker,
                state_path=state,
                boot_id_path=boot,
                runner=runner,
            )
            self.assertIn("planification impossible", message)
            self.assertFalse(state.exists())

    def test_verify_detects_unchanged_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            REBOOT.write_state(state, {"boot_id": "same"})
            boot = root / "boot-id"
            boot.write_text("same\n", encoding="utf-8")
            message = REBOOT.verify(
                state_path=state,
                boot_id_path=boot,
                marker=root / "missing",
            )
            self.assertIn("boot ID inchangé", message)
            self.assertFalse(state.exists())

    def test_verify_new_boot_checks_services_containers_vpn_and_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            REBOOT.write_state(state, {"boot_id": "old"})
            boot = root / "boot-id"
            boot.write_text("new\n", encoding="utf-8")
            docker_rows = "\n".join(
                f"{name}|running|Up 5 minutes (healthy)"
                for name in sorted(REBOOT.REQUIRED_CONTAINERS)
            )
            calls = []

            def runner(argv, *, timeout=30, sudo=False):
                calls.append((tuple(argv), sudo))
                if argv[:2] == ["/usr/bin/systemctl", "is-active"]:
                    return REBOOT.CommandResult(0, "active\n")
                if argv[:3] == ["/usr/bin/systemctl", "--user", "is-active"]:
                    return REBOOT.CommandResult(0, "active\n")
                if argv[:2] == ["/usr/bin/systemctl", "--failed"]:
                    return REBOOT.CommandResult(0, "")
                if argv[:2] == ["/usr/bin/docker", "ps"]:
                    return REBOOT.CommandResult(0, docker_rows)
                if argv[0] == "/usr/bin/ping":
                    return REBOOT.CommandResult(0)
                raise AssertionError(argv)

            message = REBOOT.verify(
                state_path=state,
                boot_id_path=boot,
                marker=root / "missing",
                runner=runner,
                endpoints=lambda: {
                    "Caddy/Authentik": True,
                    "NetBox": True,
                    "Authentik": True,
                    "Semaphore": True,
                    "OpenBao": True,
                },
            )
            self.assertIn("entièrement opérationnel", message)
            self.assertFalse(state.exists())
            self.assertTrue(any(call[0][0] == "/usr/bin/docker" for call in calls))
            self.assertTrue(any(call[0][0] == "/usr/bin/ping" for call in calls))


if __name__ == "__main__":
    unittest.main()
