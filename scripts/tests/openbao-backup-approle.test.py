#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "provision-openbao-backup-approle.py"
SPEC = importlib.util.spec_from_file_location("openbao_backup_approle", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CredentialReplacementTests(unittest.TestCase):
    old = {"role_id": "role", "secret_id": "old"}
    new = {"role_id": "role", "secret_id": "new"}

    def harness(self, fail_validate=False, fail_publish=None, fail_revoke=None):
        events = []

        def issue():
            events.append("issue:new")
            return self.new

        def validate(credentials):
            events.append(f"validate:{credentials['secret_id']}")
            if fail_validate:
                raise ValueError("validation failed")

        def publish(credentials):
            name = credentials["secret_id"]
            events.append(f"publish:{name}")
            if fail_publish == name:
                raise OSError("publish failed")

        def revoke(credentials):
            name = credentials["secret_id"]
            events.append(f"revoke:{name}")
            if fail_revoke == name:
                raise RuntimeError("revoke failed")

        return events, issue, validate, publish, revoke

    def test_rotation_publishes_before_revoking_old(self):
        events, issue, validate, publish, revoke = self.harness()
        MODULE.replace_credentials(self.old, issue, validate, publish, revoke)
        self.assertEqual(
            events,
            ["issue:new", "validate:new", "publish:new", "revoke:old"],
        )

    def test_validation_failure_revokes_only_new(self):
        events, issue, validate, publish, revoke = self.harness(fail_validate=True)
        with self.assertRaises(ValueError):
            MODULE.replace_credentials(self.old, issue, validate, publish, revoke)
        self.assertEqual(events, ["issue:new", "validate:new", "revoke:new"])

    def test_publish_failure_revokes_only_new(self):
        events, issue, validate, publish, revoke = self.harness(fail_publish="new")
        with self.assertRaises(OSError):
            MODULE.replace_credentials(self.old, issue, validate, publish, revoke)
        self.assertEqual(
            events,
            ["issue:new", "validate:new", "publish:new", "revoke:new"],
        )

    def test_old_revoke_failure_rolls_back_and_revokes_new(self):
        events, issue, validate, publish, revoke = self.harness(fail_revoke="old")
        with self.assertRaisesRegex(RuntimeError, "rolled back"):
            MODULE.replace_credentials(self.old, issue, validate, publish, revoke)
        self.assertEqual(
            events,
            [
                "issue:new",
                "validate:new",
                "publish:new",
                "revoke:old",
                "publish:old",
                "revoke:new",
            ],
        )


if __name__ == "__main__":
    unittest.main()
