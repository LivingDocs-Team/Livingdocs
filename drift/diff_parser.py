"""Unified diff parser (LD-146): turns `git diff` output of a pull request into FileChange objects."""
from __future__ import annotations

import re
from typing import List, Optional

from .models import FileChange, FileStatus, Hunk

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_QUOTED_HEADER = re.compile(r'^diff --git ("(?:[^"\\]|\\.)*"|\S+) ("(?:[^"\\]|\\.)*"|\S+)\s*$')


def _split_git_header(line: str):
    """'diff --git a/x b/y' -> ('x', 'y'); also handles quoted paths and paths with spaces."""
    if not line.startswith("diff --git "):
        return None
    m = _QUOTED_HEADER.match(line)
    if m:
        return _clean_path(m.group(1)), _clean_path(m.group(2))
    rest = line[len("diff --git "):]
    cut = rest.rfind(" b/")
    if cut > 0:
        return _clean_path(rest[:cut]), _clean_path(rest[cut + 1:])
    return None


def _unquote(path: str) -> str:
    """Undo git's C-style quoting ("a/caf\\303\\251.py")."""
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        body = path[1:-1]
        raw = bytearray()
        i = 0
        simple = {"n": 10, "t": 9, "r": 13, '"': 34, "\\": 92}
        while i < len(body):
            ch = body[i]
            if ch == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                if nxt in "01234567":
                    octal = body[i + 1:i + 4]
                    raw.append(int(octal, 8) & 0xFF)
                    i += 1 + len(octal)
                    continue
                if nxt in simple:
                    raw.append(simple[nxt])
                    i += 2
                    continue
            raw += ch.encode("utf-8")
            i += 1
        return raw.decode("utf-8", errors="replace")
    return path


def _clean_path(raw: str) -> Optional[str]:
    """'a/src/x.py<TAB>timestamp' -> 'src/x.py'; '/dev/null' -> None."""
    raw = raw.split("\t", 1)[0].strip()
    raw = _unquote(raw)
    if raw == "/dev/null":
        return None
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    return raw


def parse_unified_diff(text: str) -> List[FileChange]:
    """Parse a unified diff (git or plain `diff -u`) into a list of FileChange."""
    files: List[FileChange] = []
    current: Optional[FileChange] = None
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    hunk: Optional[Hunk] = None
    old_left = new_left = 0
    has_git_header = False

    def finish() -> None:
        nonlocal current, hunk
        if current is None:
            return
        if current.status == FileStatus.RENAMED and old_path:
            current.old_path = old_path
        files.append(current)
        current, hunk = None, None

    for line in text.splitlines():
        # Body of a hunk: consume exactly the announced number of lines.
        if hunk is not None and (old_left > 0 or new_left > 0):
            if line.startswith("\\"):
                continue
            if line.startswith("+"):
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1
            else:  # context line (an empty line is a context line whose space was trimmed)
                old_left -= 1
                new_left -= 1
                if not line.startswith(" "):
                    line = " " + line
            hunk.lines.append(line)
            continue
        if line.startswith("\\"):
            continue

        header = _split_git_header(line)
        if header:
            finish()
            has_git_header = True
            old_path, new_path = header
            current = FileChange(path=new_path or old_path or "", status=FileStatus.MODIFIED)
            continue

        if line.startswith("--- "):
            if current is None or (not has_git_header and current.hunks):
                finish()  # plain `diff -u` output: the `---` line opens a new file
                current = FileChange(path="", status=FileStatus.MODIFIED)
            if not current.hunks:
                old_path = _clean_path(line[4:])
                if old_path is None:
                    current.status = FileStatus.ADDED
                continue
        if line.startswith("+++ ") and current is not None and not current.hunks:
            new_path = _clean_path(line[4:])
            if new_path is None:
                current.status = FileStatus.DELETED
                current.path = old_path or current.path
            else:
                current.path = new_path
            continue

        hm = _HUNK.match(line)
        if hm and current is not None:
            old_start, old_count, new_start, new_count = (
                int(hm.group(1)), int(hm.group(2) or 1), int(hm.group(3)), int(hm.group(4) or 1))
            hunk = Hunk(old_start, old_count, new_start, new_count)
            current.hunks.append(hunk)
            old_left, new_left = old_count, new_count
            continue

        if current is not None and not current.hunks:
            if line.startswith("new file mode"):
                current.status = FileStatus.ADDED
            elif line.startswith("deleted file mode"):
                current.status = FileStatus.DELETED
                current.path = old_path or current.path
            elif line.startswith("rename from "):
                old_path = _unquote(line[len("rename from "):].strip())
                current.status = FileStatus.RENAMED
            elif line.startswith("rename to "):
                current.path = _unquote(line[len("rename to "):].strip())
                current.status = FileStatus.RENAMED
            elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
                current.binary = True
            continue


    finish()
    return [f for f in files if f.path]


def reconstruct_old(new_text: Optional[str], change: FileChange) -> Optional[str]:
    """Rebuild the pre-change content of a file from its post-change content and its diff.

    Lets the detector work from a diff file and a checkout alone, without git history.
    Returns None for added files (no previous version exists).
    """
    if change.status == FileStatus.ADDED:
        return None
    old_side = lambda h: [l[1:] for l in h.lines if l[:1] in (" ", "-")]  # noqa: E731
    if change.status == FileStatus.DELETED or new_text is None:
        return "\n".join(l for h in change.hunks for l in old_side(h)) + "\n"

    new_lines = new_text.splitlines()
    out: List[str] = []
    cursor = 0
    for h in change.hunks:
        start = h.new_start - 1 if h.new_count > 0 else h.new_start
        out += new_lines[cursor:start]
        out += old_side(h)
        cursor = start + h.new_count
    out += new_lines[cursor:]
    return "\n".join(out) + "\n"
