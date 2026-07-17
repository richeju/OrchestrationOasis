#!/usr/bin/env python3
"""Fail a deployment when its resolved Ansible playbook targets zero hosts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

HOST_COUNT_RE = re.compile(r"^\s*hosts \((\d+)\):\s*$", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--playbook", required=True)
    parser.add_argument("--tags")
    args = parser.parse_args()

    command = [
        "ansible-playbook",
        args.playbook,
        "--inventory",
        args.inventory,
        "--list-hosts",
    ]
    if args.tags:
        command.extend(["--tags", args.tags])

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        sys.stderr.write(output)
        return result.returncode

    counts = [int(value) for value in HOST_COUNT_RE.findall(output)]
    if not counts or sum(counts) == 0:
        target = f" tags={args.tags}" if args.tags else ""
        print(
            f"Refusing deployment: {args.playbook}{target} resolves to zero hosts.",
            file=sys.stderr,
        )
        return 1

    print(
        f"ansible_targets=passed play_occurrences={sum(counts)} "
        f"nonempty_plays={sum(value > 0 for value in counts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
