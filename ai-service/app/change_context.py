"""Context retrieval for code changes (LD-338).

For every code entity a Pull Request / commit changes, collect what a writer (person or AI)
needs to update the documentation:

- X1   the diff lines inside the entity (what changed);
- C1.. related code from the repository at the head commit: code that calls the changed
       entity, code it now uses, and similar code (TF-IDF retrieval of LD-335/337);
- D1.. documentation: first the passages that name the changed entity (they are what must be
       updated, found by the drift search of LD-148), then related passages from retrieval.

Each entity gets a ready-to-send `prompt` text citing those ids. Nothing is stored and no AI
is called: this only gathers the context.
"""
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from .drift_affected import DocText, Hit, collect_docs, find_affected
from .drift_changes import analyze_pull_request, numbered
from .drift_models import (DriftAnalyzeRequest, EntityChange, EntityChangeType, FileChangeSummary,
                           PullRequestAnalysis, PullRequestInfo)
from .models import ContextDocument, FileAnalysis, GenerateRequest, IndexSummary
from .normalize import normalize
from .retrieval import (MAX_EXCERPT_CHARS, Chunk, Links, RetrievalIndex, build_index, identifiers,
                        split_document, tokenize)

MAX_DIFF_LINES = 60          # diff lines kept per entity
MAX_MENTIONS = 10            # passages that name the entity (all of them need updating)
SIGNATURE_WEIGHT = 2         # name / signature tokens count twice in the query
SIMILAR_MIN_SCORE = 0.30     # code that is only textually similar must be clearly so
RELATED_DOC_MIN_SCORE = 0.15  # same for documentation that does not name the entity


# ---------- API models ----------

class ChangeContextRequest(DriftAnalyzeRequest):
    repository_files: List[FileAnalysis] = Field(default_factory=list)
    """Analyses of the other files of the repository at the head commit, to find related code.
    A changed file's own `after` analysis is used for that file."""
    k_code: int = Field(default=4, ge=0, le=10)
    k_docs: int = Field(default=3, ge=0, le=10)


class DiffContext(BaseModel):
    ref: str = "X1"
    path: str
    old_line_start: Optional[int] = None
    old_line_end: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    added: int = 0
    removed: int = 0
    lines: List[str] = Field(default_factory=list)       # with their '+', '-', ' ' prefix
    truncated: bool = False


class ContextItem(BaseModel):
    ref: str                                  # C1.. / D1..
    kind: str                                 # code | doc
    relation: str
    """code: handler (function serving a changed endpoint) | caller (uses the changed entity) |
    callee (the changed entity uses it) | similar;
    doc: mentions (names the changed entity: must be checked) | file_doc (saved documentation
    generated from the changed file, where a new entity belongs) | related"""
    path: str
    name: str
    entity: str = ""                          # class | method | function | endpoint | section
    section: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    score: float = 0.0
    excerpt: str
    document_id: Optional[str] = None         # saved document the passage belongs to
    version: Optional[int] = None
    matched: List[str] = Field(default_factory=list)   # mentions: the names found in the passage


class EntityContext(BaseModel):
    path: str
    previous_path: Optional[str] = None
    kind: str
    name: str
    old_name: Optional[str] = None
    change: EntityChangeType
    old_signature: Optional[str] = None
    new_signature: Optional[str] = None
    details: List[str] = Field(default_factory=list)
    diff: Optional[DiffContext] = None
    code: List[ContextItem] = Field(default_factory=list)
    docs: List[ContextItem] = Field(default_factory=list)
    prompt: str = ""


class ChangeContextReport(BaseModel):
    repository: Optional[str] = None
    pull_request: PullRequestInfo
    tickets: List[str] = Field(default_factory=list)
    index: IndexSummary
    entities: List[EntityContext] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ---------- index of the repository at the head commit ----------

def head_files(req: ChangeContextRequest) -> List[FileAnalysis]:
    """Head analyses: changed files' `after`, then the other repository files (no duplicates;
    removed files are left out)."""
    out: Dict[str, FileAnalysis] = {}
    removed = {cf.path for cf in req.files if cf.status.value == "removed"}
    removed |= {cf.previous_path for cf in req.files if cf.previous_path}
    for cf in req.files:
        if cf.after is not None and cf.status.value != "removed":
            out[cf.path] = cf.after
    for f in req.repository_files:
        if f.path not in out and f.path not in removed:
            out[f.path] = f
    files = [normalize(f.model_copy(deep=True)) for f in out.values()]
    return files


def doc_contexts(docs: List[DocText]) -> List[ContextDocument]:
    return [ContextDocument(path=d.path, title=d.title, content=d.text) for d in docs if d.text.strip()]


class _Scope:   # build_index only reads `scope.value`
    class repository:
        value = "repository"


def build_change_index(req: ChangeContextRequest, docs: List[DocText]) -> RetrievalIndex:
    gen = GenerateRequest.model_construct(scope=_Scope.repository, target=req.repository or "repository",
                                          files=head_files(req), context=doc_contexts(docs))
    return build_index(gen)


# ---------- one entity ----------

def short(name: str) -> str:
    """'Cart.total' -> 'total'; 'GET /carts/{id}' stays as it is."""
    return name if " " in name else name.rsplit(".", 1)[-1]


def diff_context(f: FileChangeSummary, c: EntityChange) -> Optional[DiffContext]:
    new_r = (c.line_start, c.line_end or c.line_start) if c.line_start else None
    old_r = (c.old_line_start, c.old_line_end or c.old_line_start) if c.old_line_start else None
    lines: List[str] = []
    for h in f.hunks:
        keep = []
        for o, n, line in numbered(h):
            inside = (new_r and n is not None and new_r[0] <= n <= new_r[1]) or \
                     (old_r and o is not None and old_r[0] <= o <= old_r[1])
            if inside:
                keep.append(line)
        if not keep and not new_r and not old_r and short(c.old_name or c.name) in h.header:
            keep = list(h.lines)          # patch-only mode without line numbers: the hunk named
        if keep and any(x[:1] in "+-" for x in keep):
            lines += keep
    if not lines:
        return None
    return DiffContext(path=f.path, old_line_start=c.old_line_start, old_line_end=c.old_line_end,
                       line_start=c.line_start, line_end=c.line_end,
                       added=sum(1 for x in lines if x.startswith("+")),
                       removed=sum(1 for x in lines if x.startswith("-")),
                       lines=lines[:MAX_DIFF_LINES], truncated=len(lines) > MAX_DIFF_LINES)


def entity_names(c: EntityChange) -> Set[str]:
    """Names other code uses to refer to the entity (before and after the change)."""
    names = set()
    for n in (c.name, c.old_name):
        if not n or " " in n:              # endpoints are not called by name
            continue
        names.add(short(n))
        if c.kind == "class":
            names.add(n)
    return names


def query_of(c: EntityChange, diff: Optional[DiffContext]) -> Counter:
    head = " ".join(x for x in (c.name, c.old_name, c.old_signature, c.new_signature) if x)
    parts = [c.old_docstring or "", c.new_docstring or "", " ".join(c.details),
             " ".join(c.removed_parameters + c.added_parameters)]
    if diff:
        parts += [x[1:] for x in diff.lines if x[:1] in "+-"]
    q = Counter(tokenize(" ".join(parts)))
    for t in tokenize(head):
        q[t] += SIGNATURE_WEIGHT
    return q


def links_of(c: EntityChange, diff: Optional[DiffContext], handler: Optional[str] = None) -> Links:
    defines = entity_names(c)
    texts = [c.new_signature, handler] + ([x[1:] for x in diff.lines if x.startswith("+")] if diff else [])
    return Links(uses=identifiers(*texts) - defines, defines=defines)


def endpoint_handlers(req: DriftAnalyzeRequest) -> Dict[Tuple[str, str], str]:
    """(file, "GET /path") -> handler name, from the head (else base) analysis of changed files."""
    out: Dict[Tuple[str, str], str] = {}
    for cf in req.files:
        for fa in (cf.before, cf.after):          # after wins
            for e in (fa.endpoints if fa else []):
                if e.handler:
                    out[(cf.path, f"{e.http_method} {e.path}")] = e.handler
    return out


def _is_self(ch: Chunk, f: FileChangeSummary, c: EntityChange) -> bool:
    if ch.path not in (f.path, f.previous_path):
        return False
    if ch.name in (c.name, c.old_name):
        return True
    return c.kind == "class" and ch.name.startswith(f"{c.name}.")   # its own methods


def related_code(index: RetrievalIndex, f: FileChangeSummary, c: EntityChange,
                 q: Counter, links: Links, k: int, handler: Optional[str] = None) -> List[ContextItem]:
    if k == 0:
        return []
    out = []
    handler_name = handler.rsplit(".", 1)[-1] if handler else None
    for ch in index.search(q, "code", None, k + 8, links):
        if _is_self(ch, f, c):
            continue
        if handler_name and ch.path == f.path and short(ch.name) == handler_name:
            relation = "handler"
        elif ch.refs & links.defines:
            relation = "caller"
        elif ch.name in links.uses or ch.name.split(".")[0] in links.uses:
            relation = "callee"
        elif ch.score >= SIMILAR_MIN_SCORE:
            relation = "similar"
        else:
            continue
        out.append(ContextItem(ref="", kind="code", relation=relation, path=ch.path, name=ch.name,
                               entity=ch.entity, line_start=ch.line_start, line_end=ch.line_end,
                               score=ch.score, excerpt=ch.excerpt))
        if len(out) == k:
            break
    order = {"handler": 0, "caller": 1, "callee": 2, "similar": 3}
    out.sort(key=lambda x: (order[x.relation], -x.score))
    return out


def _passage(doc: DocText, line: int) -> Tuple[Optional[Chunk], List[Chunk]]:
    chunks = split_document(ContextDocument(path=doc.path, title=doc.title, content=doc.text))
    for ch in chunks:
        if ch.line_start and ch.line_end and ch.line_start <= line <= ch.line_end:
            return ch, chunks
    return None, chunks


def mention_items(hits: List[Hit]) -> List[ContextItem]:
    """Passages that name the changed entity, one per passage, in document order."""
    out: Dict[Tuple, ContextItem] = {}
    for hit in hits:
        if hit.documents_file and not hit.matches:
            _, chunks = _passage(hit.doc, 0)
            if chunks:
                ch = chunks[0]
                out.setdefault((hit.doc.document_id, hit.doc.path, ch.line_start), ContextItem(
                    ref="", kind="doc", relation="file_doc", path=hit.doc.path, name=ch.name,
                    entity="section", section=ch.section or None, line_start=ch.line_start,
                    line_end=ch.line_end, score=1.0, excerpt=ch.excerpt[:MAX_EXCERPT_CHARS],
                    document_id=hit.doc.document_id, version=hit.doc.version))
        for m in hit.matches + hit.param_matches:
            ch, _ = _passage(hit.doc, m.line)
            start = ch.line_start if ch else m.line
            key = (hit.doc.document_id, hit.doc.path, start)
            if key not in out:
                out[key] = ContextItem(
                    ref="", kind="doc", relation="mentions", path=hit.doc.path,
                    name=ch.name if ch else (hit.doc.title or hit.doc.path), entity="section",
                    section=(ch.section or None) if ch else None, line_start=start,
                    line_end=ch.line_end if ch else m.line, score=1.0,
                    excerpt=(ch.excerpt if ch else m.excerpt)[:MAX_EXCERPT_CHARS],
                    document_id=hit.doc.document_id, version=hit.doc.version)
            if m.term not in out[key].matched:
                out[key].matched.append(m.term)
    return list(out.values())[:MAX_MENTIONS]


def related_docs(index: RetrievalIndex, q: Counter, links: Links, k: int,
                 taken: List[ContextItem], docs_by_path: Dict[str, DocText]) -> List[ContextItem]:
    if k == 0:
        return []
    out = []
    for ch in index.search(q, "doc", None, k + len(taken), links):
        if any(t.path == ch.path and t.line_start == ch.line_start for t in taken):
            continue
        if ch.score < RELATED_DOC_MIN_SCORE:
            break                          # results are sorted by score
        d = docs_by_path.get(ch.path)
        out.append(ContextItem(ref="", kind="doc", relation="related", path=ch.path, name=ch.name,
                               entity="section", section=ch.section or None,
                               line_start=ch.line_start, line_end=ch.line_end, score=ch.score,
                               excerpt=ch.excerpt, document_id=d.document_id if d else None,
                               version=d.version if d else None))
        if len(out) == k:
            break
    return out


# ---------- prompt text ----------

CHANGE_WORDS = {"added": "was added", "removed": "was removed", "renamed": "was renamed",
                "signature_changed": "changed its signature", "behavior_changed": "changed its behaviour"}


def _loc(path: str, a: Optional[int], b: Optional[int]) -> str:
    if a and b and b != a:
        return f"{path}:{a}-{b}"
    return f"{path}:{a}" if a else path


def prompt_of(e: EntityContext) -> str:
    title = f"{e.kind} `{e.name}` in {e.path}"
    if e.old_name:
        title = f"{e.kind} `{e.old_name}` -> `{e.name}` in {e.path}"
    out = [f"Changed code: {title} {CHANGE_WORDS[e.change.value]}."]
    if e.old_signature and e.old_signature != e.new_signature:
        out.append(f"Before: {e.old_signature}")
    if e.new_signature:
        out.append(f"After: {e.new_signature}")
    out += [f"- {d}" for d in e.details]
    if e.diff:
        out += ["", f"{e.diff.ref}: diff ({_loc(e.path, e.diff.line_start, e.diff.line_end)})", "```diff",
                *e.diff.lines, *(["... (diff truncated)"] if e.diff.truncated else []), "```"]
    mentions = [d for d in e.docs if d.relation == "mentions"]
    if mentions:
        out += ["", "Documentation that names this code (check and update it):"]
        out += _items(mentions)
    own = [d for d in e.docs if d.relation == "file_doc"]
    if own:
        out += ["", "Documentation generated from this file (where new code should be described):"]
        out += _items(own)
    if e.code:
        out += ["", "Related code at the head commit:"]
        out += _items(e.code)
    related = [d for d in e.docs if d.relation == "related"]
    if related:
        out += ["", "Other related documentation:"]
        out += _items(related)
    return "\n".join(out)


def _items(items: List[ContextItem]) -> List[str]:
    out = []
    for it in items:
        label = it.name if it.kind == "code" else (it.section or it.name)
        out.append(f"- {it.ref} [{it.relation}]: {label} ({_loc(it.path, it.line_start, it.line_end)})")
        out += ["  " + line for line in it.excerpt.splitlines()]
    return out


# ---------- whole request ----------

def entity_context(index: RetrievalIndex, f: FileChangeSummary, c: EntityChange, hits: List[Hit],
                   docs_by_path: Dict[str, DocText], k_code: int, k_docs: int,
                   handler: Optional[str] = None) -> EntityContext:
    diff = diff_context(f, c)
    q, links = query_of(c, diff), links_of(c, diff, handler)
    mentions = mention_items(hits)
    e = EntityContext(path=f.path, previous_path=f.previous_path, kind=c.kind, name=c.name,
                      old_name=c.old_name, change=c.change, old_signature=c.old_signature,
                      new_signature=c.new_signature, details=c.details, diff=diff,
                      code=related_code(index, f, c, q, links, k_code, handler),
                      docs=mentions + related_docs(index, q, links, k_docs, mentions, docs_by_path))
    for i, it in enumerate(e.code, start=1):
        it.ref = f"C{i}"
    for i, it in enumerate(e.docs, start=1):
        it.ref = f"D{i}"
    e.prompt = prompt_of(e)
    return e


def change_context(req: ChangeContextRequest, store) -> ChangeContextReport:
    analysis: PullRequestAnalysis = analyze_pull_request(req.pull_request, req.files, req.repository)
    docs, warnings = collect_docs(store, req.document_ids, req.docs)
    _, hits = find_affected(analysis, docs)
    index = build_change_index(req, docs)
    docs_by_path = {d.path: d for d in docs}
    handlers = endpoint_handlers(req)
    out = []
    for f in analysis.files:
        warnings.extend(f.warnings)
        if not f.entity_changes and f.status.value not in ("removed",):
            warnings.append(f"{f.path}: no changed class, function or endpoint was found.")
        for c in f.entity_changes:
            own = [h for h in hits if h.target.change is c]
            handler = handlers.get((f.path, c.name)) if c.kind == "endpoint" else None
            out.append(entity_context(index, f, c, own, docs_by_path, req.k_code, req.k_docs, handler))
    if not docs:
        warnings.append("No documentation was given: no saved document and no Markdown file in the request.")
    st = index.stats()
    return ChangeContextReport(repository=req.repository, pull_request=req.pull_request,
                               tickets=analysis.tickets,
                               index=IndexSummary(files=st.files, documents=st.documents,
                                                  chunks=st.chunks, vocabulary=st.vocabulary),
                               entities=out, warnings=warnings)
