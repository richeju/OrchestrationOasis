#!/usr/bin/env python3
import datetime as dt
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "daily-security-audit.py"
SPEC = importlib.util.spec_from_file_location("daily_security_audit", SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class DailySecurityAuditTests(unittest.TestCase):
    def test_public_listener_parser_excludes_private_and_loopback(self):
        sample = """
tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:*
udp UNCONN 0 0 *:1194 *:*
udp UNCONN 0 0 0.0.0.0:68 0.0.0.0:*
tcp LISTEN 0 128 10.78.0.1:8000 0.0.0.0:*
tcp LISTEN 0 128 127.0.0.1:9001 0.0.0.0:*
tcp LISTEN 0 128 213.32.65.233:443 0.0.0.0:*
"""
        self.assertEqual(
            AUDIT.parse_public_listeners(sample),
            [
                {"protocol": "tcp", "port": "22"},
                {"protocol": "tcp", "port": "443"},
                {"protocol": "udp", "port": "1194"},
            ],
        )

    def test_rogue_recency_supports_seconds_and_milliseconds(self):
        now = 1_800_000_000.0
        rows = [
            {"is_rogue": True, "essid": "Gods", "last_seen": now - 60},
            {"is_rogue": True, "essid": "Other", "last_seen": (now - 900) * 1000},
            {"is_rogue": True, "essid": "Old", "last_seen": now - 90_000},
        ]
        result = AUDIT.classify_rogues(rows, now=now)
        self.assertEqual([row["ssid"] for row in result["active"]], ["Gods"])
        self.assertEqual([row["ssid"] for row in result["recent"]], ["Other"])
        self.assertEqual([row["ssid"] for row in result["historical"]], ["Old"])
        self.assertTrue(result["active"][0]["known_ssid"])

    def test_known_ssids_are_derived_from_adopted_radios(self):
        now = 1_800_000_000.0
        summary = AUDIT.summarize_unifi(
            [{"adopted": True, "state": 1, "vap_table": [{"essid": "Derived SSID"}]}],
            [],
            [{"is_rogue": True, "essid": "Derived SSID", "last_seen": now - 60}],
            now=now,
        )
        self.assertTrue(
            summary["rogue_detections"]["active"][0]["known_ssid"]
        )

    def test_restic_summary_drops_paths_journal_and_lock_ids(self):
        failure = AUDIT.CommandResult(1, "", "repository=https://secret.example/token", None)
        self.assertEqual(
            AUDIT.error_record("restic", failure),
            {"probe": "restic", "error": "exit_1"},
        )

        raw = {
            "status": "ok",
            "reasons": [],
            "service": {"Result": "success", "ExecMainStatus": "0"},
            "timer": {"NextElapseUSecRealtime": "tomorrow"},
            "snapshot_count": 20,
            "latest_snapshot": {"age_hours": 4.2, "paths": ["/secret/path"]},
            "locks": ["sensitive-lock-id"],
            "application_backup_complete": True,
            "journal_tail": ["raw log"],
        }
        summary = AUDIT.sanitize_restic(raw)
        encoded = json.dumps(summary)
        self.assertEqual(summary["locks_count"], 1)
        self.assertNotIn("secret/path", encoded)
        self.assertNotIn("sensitive-lock-id", encoded)
        self.assertNotIn("raw log", encoded)

    def test_ufw_parser_requires_active_restrictive_defaults(self):
        summary = AUDIT.parse_ufw(
            "Status: active\nDefault: deny (incoming), allow (outgoing), disabled (routed)\n"
        )
        self.assertEqual(
            summary,
            {
                "active": True,
                "default_incoming_deny": True,
                "default_outgoing_allow": True,
            },
        )

    def test_collect_emits_complete_bounded_schema(self):
        now = dt.datetime(2026, 7, 22, 8, 0, tzinfo=dt.timezone.utc)
        restic = {
            "status": "ok",
            "reasons": [],
            "service": {"Result": "success", "ExecMainStatus": "0"},
            "timer": {"NextElapseUSecRealtime": "tomorrow"},
            "snapshot_count": 20,
            "latest_snapshot": {"age_hours": 4.0},
            "locks": [],
            "application_backup_complete": True,
        }

        def runner(argv, *, timeout=20, sudo=False):
            command = tuple(argv)
            if command[:2] == ("du", "-sb"):
                return AUDIT.CommandResult(0, "12345 /var/log\n", "")
            if command[:2] == ("journalctl", "--disk-usage"):
                return AUDIT.CommandResult(0, "Archived and active journals take up 110.3M.\n", "")
            if command[:2] == ("apt", "list"):
                return AUDIT.CommandResult(0, "Listing...\npackage/stable 1 amd64 [upgradable]\n", "")
            if command[:2] == ("systemctl", "--failed"):
                return AUDIT.CommandResult(0, "", "")
            if command[:2] == ("systemctl", "is-active") or command[:3] == ("systemctl", "--user", "is-active"):
                return AUDIT.CommandResult(0, "active\n", "")
            if command[:3] == ("ss", "-H", "-lntu"):
                return AUDIT.CommandResult(0, "tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n", "")
            if command[:3] == ("ufw", "status", "verbose"):
                return AUDIT.CommandResult(0, "Status: active\nDefault: deny (incoming), allow (outgoing)\n", "")
            if command[:3] == ("journalctl", "-u", "ssh"):
                return AUDIT.CommandResult(0, "Failed password for root from 203.0.113.8 port 22 ssh2\n", "")
            if command[:2] == ("fail2ban-client", "status"):
                return AUDIT.CommandResult(0, "Currently banned: 3\nTotal banned: 20\n", "")
            if command and command[0] == "ping":
                return AUDIT.CommandResult(0, "", "")
            if command[:2] == ("docker", "ps"):
                return AUDIT.CommandResult(0, '{"Names":"netbox","State":"running","Status":"Up (healthy)"}\n', "")
            if command == ("/usr/local/sbin/infraforge-backup-audit.sh",):
                return AUDIT.CommandResult(0, json.dumps(restic), "")
            raise AssertionError(f"unexpected command: {command}")

        devices = [{"name": "AUD-1-UDM", "adopted": True, "state": 1}]
        clients = [{"hostname": "known", "first_seen": now.timestamp() - 60}]
        rogues = [{"is_rogue": True, "essid": "Gods", "last_seen": now.timestamp() - 60}]

        def unifi_reader(path):
            if path.endswith("/stat/device"):
                return devices
            if path.endswith("/stat/sta"):
                return clients
            if path.endswith("/stat/rogueap"):
                return rogues
            raise AssertionError(path)

        with (
            mock.patch.object(AUDIT, "disk_snapshot", return_value={"used_percent": 31, "free_bytes": 1, "inode_used_percent": 13}),
            mock.patch.object(AUDIT, "probe_http", return_value={"ok": True, "status": 200}),
            mock.patch.object(AUDIT, "probe_openbao", return_value={"ok": True, "status": 200, "initialized": True, "sealed": False}),
            mock.patch.object(AUDIT.Path, "exists", return_value=False),
        ):
            report = AUDIT.collect(runner=runner, now=now, unifi_reader=unifi_reader)

        self.assertEqual(report["schema_version"], 1)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["host"]["pending_updates"], 1)
        self.assertEqual(report["storage"]["journald_bytes"], 115657933)
        self.assertEqual(report["unifi"]["adopted_online"], 1)
        self.assertEqual(len(report["unifi"]["rogue_detections"]["active"]), 1)
        self.assertEqual(report["backup"]["status"], "ok")
        self.assertNotIn("UNIFI_API_KEY", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
