"""Retrieval of related code and existing documentation (LD-340).

For each file being documented we retrieve:
  - related code: classes / functions defined in OTHER analyzed files that this file
    refers to or shares vocabulary with (e.g. a service class used by an endpoint);
  - documentation context: passages of existing docs passed in `request.context`
    (README, design notes) that talk about the same things.

Ranking is TF-IDF cosine similarity over identifier-aware tokens. It needs no
external service, is deterministic and easy to test. Retrieved items are given
ids (C1.., D1..) so the AI can cite them as evidence.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import ClassInfo, ContextDocument, FileAnalysis, Function, GenerateRequest

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
    chunks.append(Chunk(
        kind="code", path=path, name=c.name,
        excerpt=(f"class {c.name}" + (f"({', '.join(c.bases)})" if c.bases else "")
                 + (f"\n{c.docstring.strip()}" if c.docstring else "")
                 + (f"\nmethods: {method_names}" if method_names else ""))[:MAX_EXCERPT_CHARS],
        tokens=Counter(tokenize(" ".join([c.name, " ".join(c.bases), c.docstring or "", method_names]))),
        line_start=c.line_start, line_end=c.line_end))
    for m in c.methods:
        chunks.append(Chunk(kind="code", path=path, name=f"{c.name}.{m.name}",
                            excerpt=_function_excerpt(m, c.name),
                            tokens=Counter(tokenize(_function_text(m) + " " + c.name)),
                            line_start=m.line_start, line_end=m.line_end))
    return chunks


def split_document(doc: ContextDocument) -> List[Chunk]:
    """Split a document into passages at headings / blank lines, keeping line numbers."""
    lines = doc.content.splitlines()
    chunks: List[Chunk] = []
    buf: List[str] = []
    start = 1
    heading = doc.title or doc.path

    def flush(end_line: int) -> None:
        text = "\n".join(buf).strip()
        if text:
            chunks.append(Chunk(kind="doc", path=doc.path, name=heading,
                                excerpt=text[:MAX_EXCERPT_CHARS],
                                tokens=Counter(tokenize(heading + " " + text)),
                                line_start=start, line_end=end_line))

    for i, line in enumerate(lines, start=1):
        is_heading = line.lstrip().startswith("#")
        size = sum(len(x) for x in buf)
        boundary = (size > MAX_DOC_CHUNK_CHARS and not line.strip()) or size > 2 * MAX_DOC_CHUNK_CHARS
        if buf and (is_heading or boundary):
            flush(i - 1)
            buf, start = [], i
        if is_heading:
            heading = line.strip("# ").strip() or heading
        buf.append(line)
    flush(len(lines))
    return chunks


class RetrievalIndex:
    def __init__(self, chunks: List[Chunk]) -> None:
        self.chunks = chunks
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
        return [c for _, c in scored[:k]]


def build_index(req: GenerateRequest) -> RetrievalIndex:
    chunks: List[Chunk] = []
    for f in req.files:
        if f.status.value != "ok":
            continue
        for c in f.classes:
            chunks.extend(_class_chunks(f.path, c))
        for fn in f.functions:
            chunks.append(Chunk(kind="code", path=f.path, name=fn.name, excerpt=_function_excerpt(fn),
                                tokens=Counter(tokenize(_function_text(fn))),
                                line_start=fn.line_start, line_end=fn.line_end))
    for doc in req.context:
        chunks.extend(split_document(doc))
    return RetrievalIndex(chunks)


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
    code = [Chunk(**{**c.__dict__}) for c in index.search(q, "code", f.path, k_code)]
    docs = [Chunk(**{**c.__dict__}) for c in index.search(q, "doc", None, k_docs)]
    for i, c in enumerate(code, start=1):
        c.ref = f"C{i}"
    for i, d in enumerate(docs, start=1):
        d.ref = f"D{i}"
    return Retrieved(code=code, docs=docs)
