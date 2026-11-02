#!/usr/bin/env python3
"""Check repository Markdown for broken local links (documentation drift guard)."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)")
REFERENCE_LINK = re.compile(r"^\s*\[[^\]]+\]:\s*(?:<([^>]+)>|(\S+))", re.MULTILINE)
SKIP_DIRS = {".git", "node_modules", "target", "dist", ".venv", "venv"}


def markdown_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.md") if not any(part in SKIP_DIRS for part in p.parts)]


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return path.name


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    targets = []
    for match in MARKDOWN_LINK.finditer(text):
        targets.append(match.group(1) or match.group(2))
    for match in REFERENCE_LINK.finditer(text):
        targets.append(match.group(1) or match.group(2))

    errors = []
    try:
        path.resolve().relative_to(ROOT.resolve())
        boundary = ROOT.resolve()
    except ValueError:
        boundary = path.resolve().parent
    for raw in targets:
        target = unquote(raw.strip())
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith("//") or not parsed.path:
            continue
        destination = (path.parent / parsed.path).resolve()
        try:
            destination.relative_to(boundary)
        except ValueError:
            errors.append(f"{_display_path(path)}: link escapes repository: {raw}")
            continue
        if not destination.exists():
            errors.append(f"{_display_path(path)}: missing local link: {raw}")
    return errors


def main() -> int:
    errors = [error for path in markdown_files() for error in check_file(path)]
    if errors:
        print("Documentation drift detected: broken local Markdown links found.")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"Documentation drift check passed: checked {len(markdown_files())} Markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
