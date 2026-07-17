#!/usr/bin/env python3
"""Validate file targets of repository-local links in tracked Markdown files."""

from __future__ import annotations

import argparse
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


class LocalHtmlLinks(HTMLParser):
    """Collect href/src attributes from raw HTML embedded in Markdown."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        for name, value in attrs:
            if value is not None and name.lower() in {"href", "src"}:
                self.targets.append(value)


def tracked_markdown_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", "*.md"],
        capture_output=True,
        check=True,
    )
    return [root / item.decode() for item in result.stdout.split(b"\0") if item]


def markdown_targets(text: str) -> list[str]:
    parser = MarkdownIt("commonmark", {"html": True})
    targets: list[str] = []
    for token in parser.parse(text):
        children = token.children or []
        for child in children:
            if child.type == "link_open":
                href = child.attrGet("href")
                if href:
                    targets.append(str(href))
            elif child.type == "image":
                src = child.attrGet("src")
                if src:
                    targets.append(str(src))
            elif child.type == "html_inline":
                html = LocalHtmlLinks()
                html.feed(child.content)
                targets.extend(html.targets)
        if token.type == "html_block":
            html = LocalHtmlLinks()
            html.feed(token.content)
            targets.extend(html.targets)
    return targets


def resolve_local_target(root: Path, document: Path, raw: str) -> Path | None:
    value = raw.strip()
    if not value or value.startswith(("#", "//")):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    if path.startswith("/"):
        return (root / path.lstrip("/")).resolve()
    return (document.parent / path).resolve()


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = argument_parser.parse_args()
    root = args.root.resolve()

    failures: list[str] = []
    checked = 0
    for document in tracked_markdown_files(root):
        text = document.read_text(encoding="utf-8")
        for raw_target in markdown_targets(text):
            resolved = resolve_local_target(root, document, raw_target)
            if resolved is None:
                continue
            checked += 1
            try:
                resolved.relative_to(root)
            except ValueError:
                failures.append(
                    f"{document.relative_to(root)}: link escapes repository: {raw_target}"
                )
                continue
            if not resolved.exists():
                failures.append(
                    f"{document.relative_to(root)}: missing local target: {raw_target}"
                )

    if failures:
        print("\n".join(failures), file=sys.stderr)
        print(
            f"markdown_local_links=failed checked={checked} failures={len(failures)}",
            file=sys.stderr,
        )
        return 1
    print(f"markdown_local_links=passed checked={checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
