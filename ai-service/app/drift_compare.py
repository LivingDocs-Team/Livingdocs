"""LD-347 Implement source-documentation comparison: what counts as a real difference.

Drift detection compares the code before / after a Pull Request with the documentation. These
helpers keep the comparison to *real* differences so the report does not raise false positives:

    code_key / line_key   comments, blank lines and whitespace are not code changes
                          (Python `#`, Java `//` and `/* */`; `//` in Python is integer division)
    declaration_free      defaults written on the `def` line belong to the signature (LD-153),
                          not to the behaviour (LD-154): a changed default is reported once
    section_rows          what follows a mention of an entity describes it only until the next
                          heading: details are never taken from the next entity's section
    acknowledged          a line that already says the code was removed / renamed / deprecated /
                          moved, or that names the new name, is not outdated
    is_change_log         CHANGELOG.md, HISTORY.md, RELEASE_NOTES.md ... describe earlier versions
                          on purpose and are not checked
"""
import re
from typing import List, Optional

HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
TRIPLE = re.compile(r"(\"\"\"|''')[\s\S]*?\1")
BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
CHANGE_LOG = re.compile(r"(^|/)(change[-_ ]?log|changes|history|news|release[-_ ]?notes|releases)"
                        r"(\.[a-z]+)?$", re.I)
ACKNOWLEDGED = re.compile(r"\b(removed|deleted|deprecated|no longer|renamed|replaced|moved|"
                          r"obsolete|dropped|superseded|replacement)\b", re.I)
PY_DECLARATION = re.compile(r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s*)*(?:async\s+)?def\s+\w+\s*\(.*?\)\s*"
                            r"(?:->[^:]*)?:", re.S)
JAVA_DECLARATION = re.compile(r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s*)*[\w<>\[\],.?\s]*\(.*?\)\s*"
                              r"(?:throws[\w.,\s]+)?\{", re.S)


# ---------- code ----------

def strip_line_comment(line: str, lang: Optional[str] = None) -> str:
    """The line without its trailing comment, quotes respected."""
    if lang is None and line.lstrip().startswith("//"):
        return ""
    marker = "//" if lang == "java" else "#"
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif line.startswith(marker, i):
            return line[:i]
        i += 1
    return line


def code_only(text: Optional[str], lang: Optional[str] = None) -> str:
    """Code without docstrings and comments."""
    text = text or ""
    if lang != "java":
        text = TRIPLE.sub(" ", text)
    if lang != "python":
        text = BLOCK_COMMENT.sub(" ", text)
    return "\n".join(strip_line_comment(line, lang) for line in text.splitlines())


def code_key(text: Optional[str], lang: Optional[str] = None) -> str:
    """What must differ for a real code change (no comments, docstrings or whitespace)."""
    return re.sub(r"\s+", "", code_only(text, lang))


def line_key(line: str, lang: Optional[str] = None) -> str:
    """One diff line without its comment and whitespace. Docstring text is kept: a changed
    docstring is a real change (LD-154)."""
    return re.sub(r"\s+", "", strip_line_comment(line, lang))


def same_lines(removed: List[str], added: List[str], lang: Optional[str] = None) -> bool:
    """The removed and added diff lines of an entity hold the same code."""
    keys = lambda lines: sorted(k for k in (line_key(x, lang) for x in lines) if k)  # noqa: E731
    return keys(removed) == keys(added)


def declaration_free(text: str) -> str:
    """The code without its declaration (decorators, parameters and their defaults)."""
    for pat in (PY_DECLARATION, JAVA_DECLARATION):
        m = pat.match(text or "")
        if m:
            return text[m.end():]
    return text or ""


def language(name: Optional[str], path: str) -> Optional[str]:
    lang = (name or "").lower()
    if not lang:
        p = path.lower()
        lang = "python" if p.endswith(".py") else "java" if p.endswith(".java") else ""
    return lang if lang in ("python", "java") else None


# ---------- documentation ----------

def section_rows(doc, start: int, window: int) -> List[int]:
    """Line indexes from `start` (a mention of an entity) to the next heading, at most `window`."""
    heads = doc.headings
    rows = []
    for i in range(start, min(len(doc.lines), start + window)):
        if i > start and i in heads:
            break
        rows.append(i)
    return rows


def acknowledged(doc, matches, new_name: Optional[str] = None) -> bool:
    """Every mention already says the code is gone or moved, or names the new name."""
    if not matches:
        return False
    for m in matches:
        line = doc.lines[m.line - 1]
        if new_name and new_name in line:
            continue
        if not ACKNOWLEDGED.search(line.replace(m.term, " ")):   # not a word of the name itself
            return False
    return True


def is_change_log(path: str) -> bool:
    return bool(CHANGE_LOG.search(path))
