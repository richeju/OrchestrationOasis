#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
checker="$repo_root/scripts/check-markdown-links.py"
test_repo=$(mktemp -d)
trap 'rm -rf "$test_repo"' EXIT

git -C "$test_repo" init --quiet
mkdir -p "$test_repo/docs"
printf 'target\n' >"$test_repo/existing.md"
printf 'target\n' >"$test_repo/docs/my file.md"
printf 'target\n' >"$test_repo/docs/a(b).md"
printf '%s\n' \
  '[voir [les détails]](existing.md)' \
  '[angle](<docs/my file.md>)' \
  '[parentheses](docs/a(b).md)' \
  '[root](/existing.md)' \
  '<a href="existing.md">HTML</a>' \
  '`[code](missing-inline.md)`' \
  '```markdown' \
  '[fenced](missing-fenced.md)' \
  '```' >"$test_repo/index.md"
printf '[untracked](missing-untracked.md)\n' >"$test_repo/notes.md"
git -C "$test_repo" add existing.md docs index.md

"$checker" --root "$test_repo" >/dev/null

printf '[bad [nested]](definitely-missing.md)\n' >"$test_repo/index.md"
if "$checker" --root "$test_repo" >/dev/null 2>&1; then
  printf 'nested-label missing link unexpectedly passed\n' >&2
  exit 1
fi

printf '<a href="definitely-missing.md">bad HTML</a>\n' >"$test_repo/index.md"
if "$checker" --root "$test_repo" >/dev/null 2>&1; then
  printf 'HTML missing link unexpectedly passed\n' >&2
  exit 1
fi

printf 'markdown link behavior tests passed\n'
