#!/usr/bin/env python3
"""Provision and reconcile a least-privilege OpenBao Raft-backup AppRole."""

import argparse
import json
import os
import ssl
import stat
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

POLICY_NAME = "infraforge-backup"
ROLE_NAME = "infraforge-backup"


def request_json(address, context, token, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"X-Vault-Token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        address.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else {}


def login(address, context, credentials):
    payload = json.dumps(credentials).encode()
    request = urllib.request.Request(
        address.rstrip("/") + "/v1/auth/approle/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        auth = json.load(response)["auth"]
    if set(auth.get("policies", [])) != {POLICY_NAME}:
        raise RuntimeError("Backup token has unexpected policies")
    return auth["client_token"]


def require_admin_denied(address, context, token):
    request = urllib.request.Request(
        address.rstrip("/") + "/v1/sys/mounts",
        headers={"X-Vault-Token": token},
    )
    try:
        urllib.request.urlopen(request, context=context, timeout=30)
    except urllib.error.HTTPError as error:
        if error.code == 403:
            return
        raise
    raise RuntimeError("Backup AppRole unexpectedly reached an administrative endpoint")


def read_existing(output):
    if not output.exists():
        return None
    mode = stat.S_IMODE(output.stat().st_mode)
    if output.stat().st_uid != 0 or mode != 0o600:
        raise SystemExit("Existing AppRole file must be root-owned with mode 0600.")
    credentials = json.loads(output.read_text(encoding="utf-8"))
    if set(credentials) != {"role_id", "secret_id"}:
        raise SystemExit("Existing AppRole file has an unexpected schema.")
    return credentials


def write_credentials(output, credentials):
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".backup-approle.", dir=output.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(credentials, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def replace_credentials(existing, issue, validate, publish, revoke):
    """Issue and publish credentials without invalidating the working identity."""
    replacement = issue()
    try:
        validate(replacement)
        publish(replacement)
    except BaseException as operation_error:
        try:
            revoke(replacement)
        except BaseException as cleanup_error:
            raise RuntimeError(
                "Replacement failed and its new SecretID could not be revoked"
            ) from cleanup_error
        raise operation_error

    if existing is None:
        return replacement

    try:
        revoke(existing)
    except BaseException as revoke_error:
        try:
            publish(existing)
        except BaseException as rollback_error:
            raise RuntimeError(
                "Old SecretID revocation and local credential rollback both failed; "
                "the validated replacement remains published"
            ) from rollback_error
        try:
            revoke(replacement)
        except BaseException as cleanup_error:
            raise RuntimeError(
                "Old SecretID revocation failed; local credentials were rolled back, "
                "but the replacement SecretID could not be revoked"
            ) from cleanup_error
        raise RuntimeError(
            "Old SecretID revocation failed; local credentials were rolled back"
        ) from revoke_error
    return replacement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="https://10.78.0.1:8200")
    parser.add_argument("--ca-file", default="/home/debian/openbao/tls/ca.crt")
    parser.add_argument("--init-file", default="/root/.config/openbao/init.json")
    parser.add_argument(
        "--output-file", default="/root/.config/openbao/backup-approle.json"
    )
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="revoke the stored SecretID and atomically issue a replacement",
    )
    args = parser.parse_args()

    if os.geteuid() != 0:
        raise SystemExit("This bootstrap must run as root.")

    output = Path(args.output_file)
    existing = read_existing(output)
    init = json.loads(Path(args.init_file).read_text(encoding="utf-8"))
    root_token = init["root_token"]
    context = ssl.create_default_context(cafile=args.ca_file)
    policy = '''path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
'''
    request_json(
        args.address,
        context,
        root_token,
        f"/v1/sys/policies/acl/{POLICY_NAME}",
        method="PUT",
        payload={"policy": policy},
    )
    request_json(
        args.address,
        context,
        root_token,
        f"/v1/auth/approle/role/{ROLE_NAME}",
        method="POST",
        payload={
            "token_policies": [POLICY_NAME],
            "token_no_default_policy": True,
            "token_ttl": "15m",
            "token_max_ttl": "30m",
            "secret_id_num_uses": 0,
            "secret_id_ttl": "0",
        },
    )
    role = request_json(
        args.address,
        context,
        root_token,
        f"/v1/auth/approle/role/{ROLE_NAME}/role-id",
    )
    role_id = role["data"]["role_id"]

    if existing and not args.rotate:
        if existing["role_id"] != role_id:
            raise SystemExit("Stored RoleID has drifted; rerun with --rotate.")
        try:
            token = login(args.address, context, existing)
            require_admin_denied(args.address, context, token)
        except (urllib.error.HTTPError, RuntimeError) as error:
            raise SystemExit(f"Stored AppRole is invalid; rerun with --rotate: {error}")
        print("OpenBao backup policy and existing AppRole reconciled and validated.")
        return

    def issue():
        secret = request_json(
            args.address,
            context,
            root_token,
            f"/v1/auth/approle/role/{ROLE_NAME}/secret-id",
            method="POST",
            payload={},
        )
        return {"role_id": role_id, "secret_id": secret["data"]["secret_id"]}

    def validate(credentials):
        token = login(args.address, context, credentials)
        require_admin_denied(args.address, context, token)

    def revoke(credentials):
        request_json(
            args.address,
            context,
            root_token,
            f"/v1/auth/approle/role/{ROLE_NAME}/secret-id/destroy",
            method="POST",
            payload={"secret_id": credentials["secret_id"]},
        )

    replace_credentials(
        existing,
        issue,
        validate,
        lambda credentials: write_credentials(output, credentials),
        revoke,
    )
    print("OpenBao backup AppRole issued and validated; credentials remain root-only.")


if __name__ == "__main__":
    main()
