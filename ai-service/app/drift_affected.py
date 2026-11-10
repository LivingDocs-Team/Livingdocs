"""LD-148 Identify affected documentation.

Which documentation may be outdated by the changes of a Pull Request (LD-146)?

Documentation checked:
- saved, versioned documents of the AI service (LD-195): every file section of the current
  (accepted) version - the section knows which source file it was generated from;
- Markdown files of the repository sent with the request (README, docs/...).

A document part is affected when
- it was generated from a changed source file (`documents changed file`), or
- it names a changed code entity, an endpoint path or a moved / deleted file path.

Matching rules (to keep false positives low):
- names match as whole identifiers (`get_user` does not match `get_users`);
- a plain lower-case word (`add`, `run`, `update`) or a name of 3 characters or less counts only
  inside `code`, a fenced code block or a heading;
- a bare method name (`add` for `Cart.add`) counts only in the section generated from the
  method's own file, unless the name is distinctive (has `_`, a capital or a digit);
- endpoint paths match with any placeholder style (`{id}`, `:id`, `<id>`); when the line writes
  an HTTP method right before the path (`DELETE /carts/{id}`), it must be the endpoint's method.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .drift_models import (AffectedDocument, ChangeStatus, DocMatch, DocSource, EntityChange,
                           EntityChangeType, FileChangeSummary, PullRequestAnalysis)

EXCERPT_CHARS = 200
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
CHANGE_LOG = re.compile(r"(^|/)(change[-_ ]?log|changes|history|news|release[-_ ]?notes|releases)"
                        r"(\.[a-z]+)?$", re.I)
"""History files (CHANGELOG.md, ...) describe old code on purpose: they never drift (LD-347)."""
PARAM_WINDOW = 25        # a removed parameter must be named this many lines after the entity
VERB_BEFORE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)`?\s*`?$", re.I)


# ---------- documentation text ----------

@dataclass
class DocText:
    source: DocSource
    path: str
    text: str
    document_id: Optional[str] = None
    title: Optional[str] = None
    version: Optional[int] = None
    documents_file: Optional[str] = None
    _lines: Optional[List[str]] = None
    _code: Optional[List[object]] = None   # per line: True (all code) or [(start, end), ...]

    @property
    def lines(self) -> List[str]:
        if self._lines is None:
            self._index()
        return self._lines

    def _index(self) -> None:
        self._lines = self.text.splitlines()
        self._code = []
        self._headings = set()
        fence: Optional[str] = None
        for i, line in enumerate(self._lines):
            s = line.strip()
            if fence:
                self._code.append(True)
                if s.startswith(fence):
                    fence = None
                continue
            m = re.match(r"^(```+|~~~+)", s)
            if m:
                fence = m.group(1)
                self._code.append(True)
            elif s.startswith("#"):
                self._code.append(True)          # headings name the documented element
                if HEADING.match(line):
                    self._headings.add(i)
            else:
                self._code.append([(m.start(), m.end()) for m in re.finditer(r"(`+)(.+?)\1", line)])

    def section(self, start: int, window: int) -> List[int]:
        """LD-347: line indexes from `start` (a mention of an entity) to the next heading, at most
        `window` lines: what follows a mention describes that entity only until the next section
        begins (headings inside code blocks do not count)."""
        if self._code is None:
            self._index()
        rows = []
        for i in range(start, min(len(self._lines), start + window)):
            if i > start and i in self._headings:
                break
            rows.append(i)
        return rows

    def in_code(self, line_no: int, col: int) -> bool:
        if self._code is None:
            self._index()
        c = self._code[line_no]
        return c is True or any(a <= col < b for a, b in c)

    def key(self) -> Tuple:
        return self.source, self.document_id, self.path


def excerpt(line: str) -> str:
    s = line.strip()
    return s if len(s) <= EXCERPT_CHARS else s[:EXCERPT_CHARS - 1] + "…"


# ---------- what to look for ----------

@dataclass
class Term:
    text: str
    target: str               # entity name or file path the term stands for
    pattern: "re.Pattern"
    code_only: bool = False   # count only inside code / headings
    own_file_only: bool = False
    full: bool = True         # False for a bare method name or a file's base name
    verb: Optional[str] = None  # endpoints: a different HTTP method written before the path
    kind: str = "name"        # name | path | module (DocMatch.kind)


def _plain_word(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z]+", name)) or len(name) <= 3


def identifier_term(text: str, target: str, own_file_only: bool = False) -> Term:
    pat = re.compile(r"(?<![\w$])" + re.escape(text) + r"(?![\w$])")
    return Term(text, target, pat, code_only=_plain_word(text), own_file_only=own_file_only,
                full=text == target)


def path_pattern(path: str) -> str:
    out, last = "", 0
    for m in re.finditer(r"\{[^}/]*\}|:\w+|<[^>/]*>", path):
        out += re.escape(path[last:m.start()]) + r"(?:\{[^}/\s]*\}|:\w+|<[^>/\s]*>)"
        last = m.end()
    return out + re.escape(path[last:])


def endpoint_terms(key: str) -> List[Term]:
    verb, _, path = key.partition(" ")
    terms = []
    if len(path) > 1:
        pat = re.compile(r"(?<![\w/.-])" + path_pattern(path.rstrip("/")) + r"/?(?![\w{:<-]|/[\w{:<])")
        terms.append(Term(key, key, pat, verb=verb))
    return terms


def file_terms(path: str) -> List[Term]:
    terms = [Term(path, path, re.compile(r"(?<![\w.-])" + re.escape(path) + r"(?![\w/-])"),
                  kind="path")]
    base = path.rsplit("/", 1)[-1]
    if base != path and "." in base:
        terms.append(Term(base, path, re.compile(r"(?<![\w./-])" + re.escape(base) + r"(?![\w/-])"),
                          code_only=True, full=False, kind="path"))
    return terms


def entity_terms(kind: str, name: str) -> List[Term]:
    if kind == "endpoint":
        return endpoint_terms(name)
    terms = [identifier_term(name, name)]
    if "." in name:
        short = name.rsplit(".", 1)[-1]
        distinctive = bool(re.search(r"[_A-Z0-9]", short)) and len(short) >= 4
        terms.append(identifier_term(short, name, own_file_only=not distinctive))
    return terms


# ---------- targets: what changed and what the documentation may still say ----------

FILE_REMOVED = "file_removed"
FILE_RENAMED = "file_renamed"
LINE_REFS = "line_references"      # LD-152: `path:12-30` references into a modified file


@dataclass
class Target:
    file: FileChangeSummary
    change: Optional[EntityChange] = None
    file_event: Optional[str] = None
    terms: List[Term] = field(default_factory=list)
    params: List[str] = field(default_factory=list)  # removed parameters to look for
    matcher: Optional[Callable[["DocText"], List[DocMatch]]] = None   # instead of `terms`

    @property
    def label(self) -> str:
        if self.change is not None:
            return self.change.old_name or self.change.name
        return self.file.previous_path or self.file.path


def targets_of(analysis: PullRequestAnalysis) -> List[Target]:
    from .drift_referential import module_terms, stale_line_refs  # imports this module

    out: List[Target] = []
    for f in analysis.files:
        if f.status == ChangeStatus.removed:
            out.append(Target(f, file_event=FILE_REMOVED,
                              terms=file_terms(f.path) + module_terms(f.path)))
        elif f.previous_path and f.status != ChangeStatus.copied:  # moved / renamed file
            out.append(Target(f, file_event=FILE_RENAMED,
                              terms=file_terms(f.previous_path) + module_terms(f.previous_path)))
        elif f.hunks:                                 # LD-152: line references into the file
            out.append(Target(f, file_event=LINE_REFS,
                              matcher=lambda doc, f=f: stale_line_refs(doc, f.path, f.path, f.hunks)))
        for c in f.entity_changes:
            if c.change == EntityChangeType.added:
                out.append(Target(f, c))              # only matters for the file's own section
                continue
            # renamed entities and endpoints whose HTTP method changed are documented by the old name
            documented = c.old_name or c.name
            params = [p for p in c.removed_parameters if p not in ("self", "cls")] \
                if c.change == EntityChangeType.signature_changed else []
            out.append(Target(f, c, terms=entity_terms(c.kind, documented), params=params))
    return out


# ---------- search ----------

@dataclass
class Hit:
    """A document part and one change it may describe in an outdated way."""
    doc: DocText
    target: Target
    matches: List[DocMatch] = field(default_factory=list)
    param_matches: List[DocMatch] = field(default_factory=list)
    documents_file: bool = False      # the part was generated from the changed file


def _documents(doc: DocText, f: FileChangeSummary) -> bool:
    return doc.documents_file is not None and doc.documents_file in (f.path, f.previous_path)


def search(doc: DocText, terms: Sequence[Term], own_file: bool) -> List[DocMatch]:
    found: Dict[Tuple[int, str], DocMatch] = {}
    for t in terms:
        if t.own_file_only and not own_file:
            continue
        for i, line in enumerate(doc.lines):
            for m in t.pattern.finditer(line):
                if t.verb:
                    written = VERB_BEFORE.search(line[:m.start()])
                    if written and written.group(1).upper() != t.verb:
                        continue
                code = doc.in_code(i, m.start())
                if t.code_only and not code:
                    continue
                k = (i, t.target)
                if k not in found or (code and not found[k].in_code):
                    found[k] = DocMatch(term=m.group(0), target=t.target, line=i + 1,
                                        excerpt=excerpt(line), in_code=code, exact=t.full,
                                        kind=t.kind)
    return sorted(found.values(), key=lambda m: m.line)


def search_params(doc: DocText, params: List[str], near: List[DocMatch]) -> List[DocMatch]:
    """Removed parameters named (in code) within PARAM_WINDOW lines after a mention of the entity."""
    out: List[DocMatch] = []
    for p in params:
        pat = re.compile(r"(?<![\w$])" + re.escape(p) + r"(?![\w$])")
        for m0 in near:
            hit = None
            for i in doc.section(m0.line - 1, PARAM_WINDOW):
                for m in pat.finditer(doc.lines[i]):
                    if doc.in_code(i, m.start()):
                        hit = DocMatch(term=p, target=p, line=i + 1, excerpt=excerpt(doc.lines[i]),
                                       in_code=True, kind="parameter", note=f"`{p}` was removed")
                        break
                if hit:
                    break
            if hit:
                out.append(hit)
                break
    return out


def find_affected(analysis: PullRequestAnalysis,
                  docs: List[DocText]) -> Tuple[List[AffectedDocument], List[Hit]]:
    targets = targets_of(analysis)
    hits: List[Hit] = []
    affected: Dict[Tuple, AffectedDocument] = {}

    def entry(doc: DocText) -> AffectedDocument:
        k = doc.key()
        if k not in affected:
            affected[k] = AffectedDocument(source=doc.source, path=doc.path,
                                           document_id=doc.document_id, title=doc.title,
                                           version=doc.version, documents_file=doc.documents_file)
        return affected[k]

    for doc in docs:
        for t in targets:
            own = _documents(doc, t.file)
            if t.matcher is not None:
                matches = t.matcher(doc)
            else:
                matches = search(doc, t.terms, own) if t.terms else []
            if not matches and not (own and (t.file_event in (FILE_REMOVED, FILE_RENAMED)
                                             or t.change is not None)):
                continue
            hit = Hit(doc, t, matches, documents_file=own)
            if t.params and matches:
                hit.param_matches = search_params(doc, t.params, matches)
            hits.append(hit)
            a = entry(doc)
            if own:
                reason = f"documents changed file {t.file.path}"
                if reason not in a.reasons:
                    a.reasons.insert(0, reason)
            for m in matches:
                reason = f"mentions `{m.target}`"
                if reason not in a.reasons:
                    a.reasons.append(reason)
                if not any(x.line == m.line and x.target == m.target for x in a.matches):
                    a.matches.append(m)
    for a in affected.values():
        a.matches.sort(key=lambda m: m.line)
    return list(affected.values()), hits


# ---------- collecting documentation ----------

def collect_docs(store, document_ids: Optional[List[str]], repo_docs) -> Tuple[List[DocText], List[str]]:
    """Current version of saved documents (by file section) + Markdown files from the request."""
    from .versions import VersionError  # local import: versions imports the generator stack

    out: List[DocText] = []
    warnings: List[str] = []
    if document_ids is None:
        docs = store.list()
    else:
        docs = []
        for doc_id in dict.fromkeys(document_ids):
            try:
                docs.append(store.get(doc_id))
            except VersionError:
                warnings.append(f"Document '{doc_id}' not found; it was not checked.")
    for d in docs:
        v = store.version(d.id)
        if v.sections and v.sections_match_content:
            for s in v.sections:
                out.append(DocText(DocSource.document, s.path, s.markdown, d.id, d.title, v.number,
                                   documents_file=s.path))
        else:  # hand-edited text that no longer splits into files: check it as one text
            single = v.sections[0].path if len(v.sections) == 1 else None
            out.append(DocText(DocSource.document, d.target, v.content, d.id, d.title, v.number,
                               documents_file=single))
    for rd in repo_docs:
        if CHANGE_LOG.search(rd.path):
            warnings.append(f"{rd.path}: change log, not checked (it describes earlier versions on purpose).")
            continue
        out.append(DocText(DocSource.repository, rd.path, rd.content, title=rd.title))
    return out, warnings
