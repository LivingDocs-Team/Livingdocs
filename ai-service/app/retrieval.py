"""Retrieval of related code and existing documentation (LD-340, LD-335).

For each file being documented we retrieve:
  - related code: classes / functions defined in OTHER analyzed files that this file
    refers to or shares vocabulary with (e.g. a service class used by an endpoint);
  - documentation context: passages of existing docs passed in `request.context`
    (README, design notes) that talk about the same things.

Ranking is TF-IDF cosine similarity over identifier-aware tokens. It needs no
external service, is deterministic and easy to test. Retrieved items are given
ids (C1.., D1..) so the AI can cite them as evidence.

Index content (LD-335): classes (with fields and method names), methods, functions and
HTTP endpoints of every analysed file, and the sections of every context document
(Markdown headings, ignoring `#` lines inside fenced code blocks, with the heading path
"Shop > Cart" kept for each passage).
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import ClassInfo, ContextDocument, Endpoint, FileAnalysis, Function, GenerateRequest

MAX_DOC_CHUNK_CHARS = 1200
MAX_EXCERPT_CHARS = 600
MIN_SCORE = 0.05

_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "into", "are", "was", "not", "def",
    "self", "cls", "return", "none", "true", "false", "class", "async", "await", "import",
    "str", "int", "float", "bool", "list", "dict", "optional", "any", "public", "private",
    "void", "static", "new", "if", "else", "in", "is", "of", "to", "a", "an", "or", "by",
    "và", "của", "các", "cho", "là", "được", "trong", "một", "những", "với", "để", "khi", "này", "có",
}


def tokenize(text: str) -> List[str]:
    """Identifier-aware tokens: getUserById -> get user by id; snake_case split too."""
    if not text:
        return []
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[A-Za-zÀ-ỹ0-9]+", text.lower())
    return [w for w in words if len(w) >= 2 and w not in _STOP and not w.isdigit()]


@dataclass
class Chunk:
    kind: str                     # "code" | "doc"
    path: str
    name: str                     # entity name or doc title
    excerpt: str
    tokens: Counter
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    ref: str = ""                 # assigned per prompt: C1, D1 ...
    entity: str = ""              # class | method | function | endpoint | section
    section: str = ""             # doc passages: heading path, e.g. "Shop > Cart"
    score: float = 0.0            # similarity to the query that retrieved it


@dataclass
class Retrieved:
    code: List[Chunk] = field(default_factory=list)
    docs: List[Chunk] = field(default_factory=list)


def _function_text(fn: Function) -> str:
    params = " ".join(f"{p.name} {p.type or ''}" for p in fn.parameters)
    return " ".join(x for x in [fn.name, fn.signature, params, fn.return_type, fn.docstring, fn.source] if x)


def _function_excerpt(fn: Function, owner: str = "") -> str:
    head = fn.signature or f"{fn.name}({', '.join(p.name for p in fn.parameters)})"
    if owner:
        head = f"{owner}.{head}"
    doc = (fn.docstring or "").strip()
    text = head + (f"\n{doc}" if doc else "")
    return text[:MAX_EXCERPT_CHARS]


def _class_chunks(path: str, c: ClassInfo) -> List[Chunk]:
    chunks = []
    method_names = " ".join(m.name for m in c.methods)
    fields = ", ".join(f"{x.name}: {x.type}" if x.type else x.name for x in c.fields)
    field_text = " ".join(f"{x.name} {x.type or ''} {x.description or ''}" for x in c.fields)
    chunks.append(Chunk(
        kind="code", path=path, name=c.name, entity="class",
        excerpt=(f"{c.kind or 'class'} {c.name}" + (f"({', '.join(c.bases)})" if c.bases else "")
                 + (f"\n{c.docstring.strip()}" if c.docstring else "")
                 + (f"\nfields: {fields}" if fields else "")
                 + (f"\nmethods: {method_names}" if method_names else ""))[:MAX_EXCERPT_CHARS],
        tokens=Counter(tokenize(" ".join([c.name, " ".join(c.bases), c.docstring or "", method_names,
                                          field_text]))),
        line_start=c.line_start, line_end=c.line_end))
    for m in c.methods:
        chunks.append(Chunk(kind="code", path=path, name=f"{c.name}.{m.name}", entity="method",
                            excerpt=_function_excerpt(m, c.name),
                            tokens=Counter(tokenize(_function_text(m) + " " + c.name)),
                            line_start=m.line_start, line_end=m.line_end))
    return chunks


def _endpoint_text(e: Endpoint) -> str:
    params = " ".join(f"{p.name} {p.type or ''}" for p in e.parameters)
    route = re.sub(r"[{}<>:]", " ", e.path)
    return " ".join(x for x in [route, e.handler, params, e.request_body, e.response] if x)


def _endpoint_chunk(path: str, e: Endpoint) -> Chunk:
    """An HTTP endpoint, so a service file can find the routes that expose it."""
    lines = [f"{e.http_method} {e.path}" + (f" -> {e.handler}" if e.handler else "")]
    if e.parameters:
        lines.append("parameters: " + ", ".join(f"{p.name}: {p.type}" if p.type else p.name
                                                 for p in e.parameters))
    if e.request_body:
        lines.append(f"request: {e.request_body}")
    if e.response:
        lines.append(f"response: {e.response}")
    return Chunk(kind="code", path=path, name=f"{e.http_method} {e.path}", entity="endpoint",
                 excerpt="\n".join(lines)[:MAX_EXCERPT_CHARS], tokens=Counter(tokenize(_endpoint_text(e))),
                 line_start=e.line_start, line_end=e.line_end)


_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


def split_document(doc: ContextDocument) -> List[Chunk]:
    """Split a document into passages at headings / blank lines, keeping line numbers.

    `#` lines inside fenced code blocks (``` or ~~~) are code (shell or Python comments), not
    headings. Each passage keeps its nearest heading as `name` and the heading path
    ("Shop > Cart") as `section`; the heading path is indexed too."""
    lines = doc.content.splitlines()
    chunks: List[Chunk] = []
    buf: List[str] = []
    start = 1
    root = doc.title or doc.path
    stack: List[tuple] = []          # (level, heading text)
    in_fence = False

    def current() -> tuple:
        return (stack[-1][1] if stack else root), " > ".join(h for _, h in stack) or root

    def flush(end_line: int) -> None:
        text = "\n".join(buf).strip()
        if text:
            name, section = current()
            chunks.append(Chunk(kind="doc", path=doc.path, name=name, entity="section",
                                section=section, excerpt=text[:MAX_EXCERPT_CHARS],
                                tokens=Counter(tokenize(section + " " + text)),
                                line_start=start, line_end=end_line))

    for i, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence or _FENCE.match(line) else _HEADING.match(line)
        size = sum(len(x) for x in buf)
        boundary = (size > MAX_DOC_CHUNK_CHARS and not line.strip() and not in_fence) \
            or size > 2 * MAX_DOC_CHUNK_CHARS
        if buf and (m or boundary):
            flush(i - 1)
            buf, start = [], i
        if m:
            level, title = len(m.group(1)), m.group(2).strip() or root
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        buf.append(line)
    flush(len(lines))
    return chunks


@dataclass
class IndexStats:
    files: int
    documents: int
    chunks: Dict[str, int]        # entity kind -> number of indexed items
    vocabulary: int


class RetrievalIndex:
    def __init__(self, chunks: List[Chunk], files: int = 0, documents: int = 0) -> None:
        self.chunks = chunks
        self.files, self.documents = files, documents
        df: Counter = Counter()
        for c in chunks:
            df.update(set(c.tokens))
        n = max(len(chunks), 1)
        self.idf: Dict[str, float] = {t: math.log((n + 1) / (d + 0.5)) + 1 for t, d in df.items()}
        self._norms = [self._norm(c.tokens) for c in chunks]

    def _weights(self, tokens: Counter) -> Dict[str, float]:
        return {t: (1 + math.log(f)) * self.idf.get(t, 1.0) for t, f in tokens.items()}

    def _norm(self, tokens: Counter) -> float:
        return math.sqrt(sum(w * w for w in self._weights(tokens).values())) or 1.0

    def stats(self) -> IndexStats:
        return IndexStats(files=self.files, documents=self.documents,
                          chunks=dict(sorted(Counter(c.entity or c.kind for c in self.chunks).items())),
                          vocabulary=len(self.idf))

    def search(self, query: Counter, kind: str, exclude_path: Optional[str], k: int) -> List[Chunk]:
        q = self._weights(query)
        q_norm = math.sqrt(sum(w * w for w in q.values())) or 1.0
        scored = []
        for c, c_norm in zip(self.chunks, self._norms):
            if c.kind != kind or (exclude_path and c.path == exclude_path):
                continue
            cw = self._weights(c.tokens)
            dot = sum(q[t] * cw[t] for t in q.keys() & cw.keys())
            score = dot / (q_norm * c_norm)
            if score >= MIN_SCORE:
                scored.append((score, c))
        scored.sort(key=lambda x: (-x[0], x[1].path, x[1].name))
        out = []
        for score, c in scored[:k]:
            hit = Chunk(**{**c.__dict__})
            hit.score = round(score, 4)
            out.append(hit)
        return out


def build_index(req: GenerateRequest) -> RetrievalIndex:
    chunks: List[Chunk] = []
    files = 0
    for f in req.files:
        if f.status.value != "ok":
            continue
        files += 1
        for c in f.classes:
            chunks.extend(_class_chunks(f.path, c))
        for fn in f.functions:
            chunks.append(Chunk(kind="code", path=f.path, name=fn.name, entity="function",
                                excerpt=_function_excerpt(fn), tokens=Counter(tokenize(_function_text(fn))),
                                line_start=fn.line_start, line_end=fn.line_end))
        for e in f.endpoints:
            chunks.append(_endpoint_chunk(f.path, e))
    for doc in req.context:
        chunks.extend(split_document(doc))
    return RetrievalIndex(chunks, files=files, documents=len(req.context))


def file_query(f: FileAnalysis) -> Counter:
    parts = [f.path, f.module or ""]
    for c in f.classes:
        parts += [c.name, " ".join(c.bases), c.docstring or ""]
        parts += [_function_text(m) for m in c.methods]
    parts += [_function_text(fn) for fn in f.functions]
    for e in f.endpoints:
        parts += [e.path, e.handler or "", e.request_body or "", e.response or ""]
    return Counter(tokenize(" ".join(parts)))


def retrieve(index: Optional[RetrievalIndex], f: FileAnalysis,
             k_code: int = 4, k_docs: int = 3) -> Retrieved:
    """Related code from other files + documentation passages for one file."""
    if index is None:
        return Retrieved()
    q = file_query(f)
    code = index.search(q, "code", f.path, k_code)
    docs = index.search(q, "doc", None, k_docs)
    for i, c in enumerate(code, start=1):
        c.ref = f"C{i}"
    for i, d in enumerate(docs, start=1):
        d.ref = f"D{i}"
    return Retrieved(code=code, docs=docs)
