"""Documentation index used to find where changed code is mentioned (LD-148)."""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import unquote, urlsplit

from .models import is_doc_path

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_CODE_SPAN = re.compile(r"(`+)([^`\n]+?)\1")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)")
_FILE_EXT_AFTER = re.compile(r"\.(?:py|java|md|json|ya?ml|js|jsx|ts|tsx|txt|xml|html|css|toml|cfg|ini|sql|sh)\b")
HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD")
_PARAM_SEGMENT = r"(?:\{[^}/]+\}|:\w+|<[^>/]+>)"
_IGNORED_DIRS = {".git", "node_modules", "target", "dist", "build", ".venv", "venv", "__pycache__"}


@dataclass(frozen=True)
class DocReference:
    """One place in a document that mentions something."""
    doc_path: str
    line: int                 # 1-based
    col_start: int
    col_end: int
    kind: str                 # code_span | code_block | heading | prose | link
    matched: str
    text: str                 # the full line
    section_title: str
    section_start: int
    section_end: int
    doc_method: Optional[str] = None   # HTTP method written before a matched route


@dataclass
class DocFile:
    path: str
    text: str
    lines: List[str] = field(default_factory=list)
    kinds: List[str] = field(default_factory=list)          # per line: code_block | heading | prose
    section_of: List[int] = field(default_factory=list)     # per line: index into sections
    sections: List[Tuple[int, int, str]] = field(default_factory=list)  # (start, end, title) 1-based
    links: List[Tuple[int, str, str]] = field(default_factory=list)     # (line, resolved path, raw)

    def section_text(self, line: int, max_lines: int = 60) -> str:
        start, end, _ = self.sections[self.section_of[line - 1]]
        return "\n".join(self.lines[start - 1:min(end, start - 1 + max_lines)])

    def code_identifiers(self, line: int) -> set:
        """Identifiers written as code (inline code, code blocks, table cells) in the line's section."""
        start, end, _ = self.sections[self.section_of[line - 1]]
        found: set = set()
        for i in range(start - 1, min(end, start + 59)):
            text, kind = self.lines[i], self.kinds[i]
            if kind == "code_block":
                found.update(re.findall(r"[A-Za-z_]\w*", text))
                continue
            for m in _CODE_SPAN.finditer(text):
                found.update(re.findall(r"[A-Za-z_]\w*", m.group(2)))
            if text.lstrip().startswith("|"):
                for cell in text.strip().strip("|").split("|"):
                    cell = cell.strip().strip("`*")
                    if re.fullmatch(r"[A-Za-z_]\w*", cell):
                        found.add(cell)
            bullet = re.match(r"^\s*[-*]\s+\*{0,2}`?([A-Za-z_]\w*)`?\*{0,2}\s*[:(\u2013\u2014-]", text)
            if bullet:
                found.add(bullet.group(1))
        return found


class DocIndex:
    def __init__(self, docs: Mapping[str, str]):
        self.docs: Dict[str, DocFile] = {p: _parse_doc(p, t) for p, t in docs.items()}

    def __len__(self) -> int:
        return len(self.docs)

    # ---- searching -------------------------------------------------------------------------

    def find_name(self, name: str) -> List[DocReference]:
        """References to a code name (`Cart.add`, `get_order`) in the docs, with context."""
        pattern = re.compile(r"(?<![\w$/])" + re.escape(name) + r"(?![\w$])")
        refs: List[DocReference] = []
        for doc in self.docs.values():
            if name not in doc.text:
                continue
            for idx, line in enumerate(doc.lines):
                for m in pattern.finditer(line):
                    if _FILE_EXT_AFTER.match(line, m.end()) and line[m.end()] == ".":
                        continue  # `cart_service.py` is a file name, not the entity
                    refs.append(_make_ref(doc, idx, m.start(), m.end(), m.group(0)))
        return refs

    def find_route(self, route: str) -> List[DocReference]:
        """References to an HTTP route ("GET /orders/{id}"); path style ({id}, :id, <id>) is ignored."""
        method, _, path = route.partition(" ")
        if not path:
            method, path = "", route
        if path.strip("/") == "":
            return []
        body = "/".join(_PARAM_SEGMENT if re.fullmatch(_PARAM_SEGMENT, seg) else re.escape(seg)
                        for seg in path.strip("/").split("/"))
        pattern = re.compile(r"(?<![\w/.\-])/" + body + r"/?(?![\w/\-])")
        refs: List[DocReference] = []
        for doc in self.docs.values():
            for idx, line in enumerate(doc.lines):
                for m in pattern.finditer(line):
                    before = line[:m.start()]
                    mm = re.search(r"\b(" + "|".join(HTTP_METHODS) + r")\W{0,3}$", before)
                    refs.append(_make_ref(doc, idx, m.start(), m.end(), m.group(0),
                                          doc_method=mm.group(1) if mm else None))
        return refs

    def find_path(self, path: str) -> List[DocReference]:
        """References to a repository file: a resolved Markdown link or a written path (full or suffix)."""
        path = path.strip("/")
        refs: List[DocReference] = []
        parts = path.split("/")
        for doc in self.docs.values():
            for line_no, resolved, raw in doc.links:
                if resolved == path:
                    idx = line_no - 1
                    col = doc.lines[idx].find(raw)
                    refs.append(_make_ref(doc, idx, max(col, 0), max(col, 0) + len(raw), raw, kind="link"))
            if len(parts) < 2 and path not in doc.text:
                continue
            pattern = re.compile(r"(?<![\w.\-])(?:\./)?" + re.escape(path) + r"(?![\w\-])")
            for idx, line in enumerate(doc.lines):
                if any(r.line == idx + 1 and r.kind == "link" for r in refs if r.doc_path == doc.path):
                    continue
                for m in pattern.finditer(line):
                    refs.append(_make_ref(doc, idx, m.start(), m.end(), m.group(0)))
        return refs


def _make_ref(doc: DocFile, idx: int, start: int, end: int, matched: str,
              kind: Optional[str] = None, doc_method: Optional[str] = None) -> DocReference:
    line_kind = doc.kinds[idx]
    if kind is None:
        if line_kind == "code_block":
            kind = "code_block"
        elif line_kind == "heading":
            kind = "heading"
        else:
            in_span = any(m.start(2) <= start and end <= m.end(2) for m in _CODE_SPAN.finditer(doc.lines[idx]))
            kind = "code_span" if in_span else "prose"
    s_start, s_end, title = doc.sections[doc.section_of[idx]]
    return DocReference(doc.path, idx + 1, start, end, kind, matched, doc.lines[idx], title,
                        s_start, s_end, doc_method)


def _parse_doc(path: str, text: str) -> DocFile:
    doc = DocFile(path=path, text=text, lines=text.replace("\r\n", "\n").split("\n"))
    in_code = False
    heading_lines: List[Tuple[int, str]] = []
    markdown = path.lower().endswith((".md", ".markdown", ".mdx"))
    for i, line in enumerate(doc.lines):
        if markdown and _FENCE.match(line):
            in_code = not in_code
            doc.kinds.append("code_block")
        elif in_code:
            doc.kinds.append("code_block")
        elif markdown and _HEADING.match(line):
            doc.kinds.append("heading")
            heading_lines.append((i + 1, _HEADING.match(line).group(2)))
        else:
            doc.kinds.append("prose")
    # sections: from each heading up to the next heading (any level)
    boundaries = [(1, "")] + heading_lines if not heading_lines or heading_lines[0][0] != 1 else heading_lines
    for n, (start, title) in enumerate(boundaries):
        end = boundaries[n + 1][0] - 1 if n + 1 < len(boundaries) else len(doc.lines)
        doc.sections.append((start, end, title))
    section = 0
    for i in range(len(doc.lines)):
        while section + 1 < len(doc.sections) and doc.sections[section + 1][0] <= i + 1:
            section += 1
        doc.section_of.append(section)
    # relative links resolved against the document folder
    base = posixpath.dirname(path)
    for i, line in enumerate(doc.lines):
        if doc.kinds[i] == "code_block":
            continue
        for m in _LINK.finditer(line):
            raw = m.group(1) or m.group(2)
            parsed = urlsplit(unquote(raw.strip()))
            if parsed.scheme or raw.startswith("//") or not parsed.path:
                continue
            resolved = posixpath.normpath(posixpath.join(base, parsed.path)) if not parsed.path.startswith("/") \
                else parsed.path.lstrip("/")
            doc.links.append((i + 1, resolved, raw))
    return doc


def is_distinctive(name: str) -> bool:
    """A name unlikely to be an ordinary word: qualified, snake_case, camelCase or long."""
    short = name.rsplit(".", 1)[-1]
    return "." in name or "_" in short or bool(re.search(r"[a-z][A-Z]", short)) or len(short) >= 10


def build_index(docs: Mapping[str, str]) -> DocIndex:
    return DocIndex(docs)


def filter_doc_paths(paths: Iterable[str], ignore: Iterable[str] = ()) -> List[str]:
    """Keep documentation files, drop vendored folders and anything matching an ignore glob."""
    import fnmatch
    ignore = list(ignore)
    kept = []
    for p in paths:
        if not is_doc_path(p):
            continue
        if any(part in _IGNORED_DIRS for part in p.split("/")):
            continue
        if any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(posixpath.basename(p), pat) for pat in ignore):
            continue
        kept.append(p)
    return sorted(kept)
