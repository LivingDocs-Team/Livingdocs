"""Retrieval of related code and existing documentation (LD-340, LD-335, LD-337).

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
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .models import ClassInfo, ContextDocument, Endpoint, FileAnalysis, Function, GenerateRequest

MAX_DOC_CHUNK_CHARS = 1200
MAX_EXCERPT_CHARS = 600
MIN_SCORE = 0.05
CALL_BONUS = 0.25        # LD-337: the file calls this code (its name is in the file's source)
CLASS_BONUS = 0.10       # the file uses the class, not necessarily this method
CALLER_BONUS = 0.20      # this code uses something the file defines
DOC_MENTION_BONUS = 0.15  # the passage names a class / function of the file
COMMON_PATH_SHARE = 0.8  # path terms found in at least this share of the files are ignored
COMMON_PATH_MIN_FILES = 4  # ... when there are at least this many files

_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "into", "are", "was", "not", "def",
    "self", "cls", "return", "none", "true", "false", "class", "async", "await", "import",
    "str", "int", "float", "bool", "list", "dict", "optional", "any", "public", "private",
    "void", "static", "new", "if", "else", "in", "is", "of", "to", "a", "an", "or", "by",
    "và", "của", "các", "cho", "là", "được", "trong", "một", "những", "với", "để", "khi", "này", "có",
}


def fold(text: str) -> str:
    """Lower case without Vietnamese diacritics: 'Hóa Đơn' -> 'hoa don' (LD-337)."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


_STOP_FOLDED = {fold(w) for w in _STOP}


def tokenize(text: str) -> List[str]:
    """Identifier-aware tokens: getUserById -> get user by id; snake_case split too.
    Diacritics are folded, so Vietnamese text matches identifiers such as HoaDon / hoa_don."""
    if not text:
        return []
    words = re.findall(r"[a-z0-9]+", fold(_split_camel(text)))
    return [singular(w) for w in words if len(w) >= 2 and w not in _STOP_FOLDED and not w.isdigit()]


def _split_camel(text: str) -> str:
    """getCartTotal -> get Cart Total; works for accented letters too (HóaĐơn -> Hóa Đơn)."""
    out = []
    for i, ch in enumerate(text):
        if i and ch.isupper() and (text[i - 1].islower() or text[i - 1].isdigit()):
            out.append(" ")
        out.append(ch)
    return "".join(out)


def singular(word: str) -> str:
    """Light English plural folding so 'products' matches product, 'categories' category."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CODE_NAME = re.compile(r"\b(?:[A-Za-z]+[a-z0-9][A-Z][A-Za-z0-9]*|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)\b")


def code_names(text: str) -> Set[str]:
    """Words in prose that look like code: CartService, getTotal, cart_id (not 'cart')."""
    return set(_CODE_NAME.findall(text or ""))


def identifiers(*texts: Optional[str]) -> Set[str]:
    """Names written in code or types: 'CartService().total(x)' -> {CartService, total, x}."""
    out: Set[str] = set()
    for t in texts:
        if t:
            out.update(_IDENT.findall(t))
    return out


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
    refs: Set[str] = field(default_factory=set)   # names this code uses (calls, types)


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


def _function_refs(fn: Function) -> Set[str]:
    return identifiers(fn.source, fn.signature, fn.return_type, *(p.type for p in fn.parameters))


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
        line_start=c.line_start, line_end=c.line_end,
        refs=identifiers(" ".join(c.bases), " ".join(x.type or "" for x in c.fields))))
    for m in c.methods:
        chunks.append(Chunk(kind="code", path=path, name=f"{c.name}.{m.name}", entity="method",
                            excerpt=_function_excerpt(m, c.name),
                            tokens=Counter(tokenize(_function_text(m) + " " + c.name)),
                            line_start=m.line_start, line_end=m.line_end, refs=_function_refs(m)))
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
                 line_start=e.line_start, line_end=e.line_end,
                 refs=identifiers(e.handler, e.request_body, e.response, *(p.type for p in e.parameters)))


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
        body = [x for i, x in enumerate(buf) if x.strip() and not (i == 0 and _HEADING.match(x))]
        if text and body:          # LD-337: a passage that is only a heading is not indexed
            name, section = current()
            chunks.append(Chunk(kind="doc", path=doc.path, name=name, entity="section",
                                section=section, excerpt=text[:MAX_EXCERPT_CHARS],
                                tokens=Counter(tokenize(section + " " + text)),
                                line_start=start, line_end=end_line, refs=code_names(text)))

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


@dataclass
class Links:
    """What a file being documented uses and defines (LD-337 bonuses)."""
    uses: Set[str] = field(default_factory=set)
    defines: Set[str] = field(default_factory=set)


def _bonus(c: Chunk, links: Optional[Links]) -> float:
    if links is None:
        return 0.0
    bonus = 0.0
    if c.kind == "code":
        if c.entity in ("class", "function") and c.name in links.uses:
            bonus += CALL_BONUS
        elif c.entity == "method":
            owner, _, method = c.name.partition(".")
            if owner in links.uses:
                bonus += CALL_BONUS if method in links.uses else CLASS_BONUS
        if c.refs & links.defines:
            bonus += CALLER_BONUS
    elif c.refs & links.defines:
        bonus += DOC_MENTION_BONUS
    return bonus


class RetrievalIndex:
    def __init__(self, chunks: List[Chunk], files: int = 0, documents: int = 0,
                 common_terms: Optional[Set[str]] = None) -> None:
        self.chunks = chunks
        self.files, self.documents = files, documents
        self.common_terms: Set[str] = set(common_terms or ())
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

    def search(self, query: Counter, kind: str, exclude_path: Optional[str], k: int,
               links: Optional[Links] = None) -> List[Chunk]:
        """TF-IDF cosine similarity, plus the LD-337 bonuses when `links` is given; capped at 1."""
        query = Counter({t: n for t, n in query.items() if t not in self.common_terms})
        q = self._weights(query)
        q_norm = math.sqrt(sum(w * w for w in q.values())) or 1.0
        scored = []
        for c, c_norm in zip(self.chunks, self._norms):
            if c.kind != kind or (exclude_path and c.path == exclude_path):
                continue
            cw = self._weights(c.tokens)
            dot = sum(q[t] * cw[t] for t in q.keys() & cw.keys())
            score = min(1.0, dot / (q_norm * c_norm) + _bonus(c, links))
            if score >= MIN_SCORE:
                scored.append((score, c))
        scored.sort(key=lambda x: (-x[0], x[1].path, x[1].name))
        out, seen = [], set()
        for score, c in scored:
            if len(out) == k:
                break
            text = " ".join(c.excerpt.split())
            if text in seen:          # LD-339: the same passage twice (copied docs) uses one slot
                continue
            seen.add(text)
            hit = Chunk(**{**c.__dict__})
            hit.score = round(score, 4)
            out.append(hit)
        return out


def common_path_terms(paths: List[str]) -> Set[str]:
    """Terms present in most file paths (repository name, src/main/java/com/...). They match
    every file, so using them in queries only pulls in generic passages (LD-336 finding)."""
    if len(paths) < COMMON_PATH_MIN_FILES:
        return set()
    counts: Counter = Counter()
    for p in paths:
        counts.update(set(tokenize(p.rsplit(".", 1)[0])))
    return {t for t, n in counts.items() if n >= COMMON_PATH_SHARE * len(paths)}


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
                                line_start=fn.line_start, line_end=fn.line_end, refs=_function_refs(fn)))
        for e in f.endpoints:
            chunks.append(_endpoint_chunk(f.path, e))
    for doc in req.context:
        chunks.extend(split_document(doc))
    paths = [f.path for f in req.files if f.status.value == "ok"]
    common = common_path_terms(paths)
    if req.scope.value == "repository":
        # the repository name used as a folder ("shop/...") says nothing about a single file
        path_terms = {t for p in paths for t in tokenize(p)}
        common |= {t for t in tokenize(req.target) if t in path_terms}
    return RetrievalIndex(chunks, files=files, documents=len(req.context), common_terms=common)


def file_query(f: FileAnalysis) -> Counter:
    parts = [f.path, f.module or ""]
    for c in f.classes:
        parts += [c.name, " ".join(c.bases), c.docstring or ""]
        parts += [_function_text(m) for m in c.methods]
    parts += [_function_text(fn) for fn in f.functions]
    for e in f.endpoints:
        parts += [e.path, e.handler or "", e.request_body or "", e.response or ""]
    return Counter(tokenize(" ".join(parts)))


def file_links(f: FileAnalysis) -> Links:
    """Names the file defines (classes, functions) and names its code uses."""
    defines = {c.name for c in f.classes} | {fn.name for fn in f.functions}
    texts: List[Optional[str]] = []
    for fn in [m for c in f.classes for m in c.methods] + list(f.functions):
        texts += [fn.source, fn.signature, fn.return_type, *(p.type for p in fn.parameters)]
    for c in f.classes:
        texts += [" ".join(c.bases), *(x.type for x in c.fields)]
    for e in f.endpoints:
        texts += [e.request_body, e.response, *(p.type for p in e.parameters)]
    return Links(uses=identifiers(*texts) - defines, defines=defines)


def retrieve(index: Optional[RetrievalIndex], f: FileAnalysis,
             k_code: int = 4, k_docs: int = 3) -> Retrieved:
    """Related code from other files + documentation passages for one file."""
    if index is None:
        return Retrieved()
    q = file_query(f)
    links = file_links(f)
    code = index.search(q, "code", f.path, k_code, links)
    docs = index.search(q, "doc", None, k_docs, links)
    for i, c in enumerate(code, start=1):
        c.ref = f"C{i}"
    for i, d in enumerate(docs, start=1):
        d.ref = f"D{i}"
    return Retrieved(code=code, docs=docs)
