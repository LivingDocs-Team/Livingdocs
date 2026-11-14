"""Documentation update suggestions (LD-353) and drift resolution suggestions (LD-354).

When a Pull Request changes code, propose concrete edits to the documentation that describes
it: for each passage that must change, the text it has now (`original`), the text it should
have (`proposed`) and why. Suggestions are kept so a reviewer can accept or reject them later.

How the proposed text is made:
- rules (always available, no AI): rename identifiers and endpoint paths, rewrite calls in the
  documented signature, remove / rename / add / retype rows of the parameter table, update the
  return type and the docstring line, delete the section of a removed entity, add a section for
  a new entity next to the ones of the same kind;
- AI (when a client is configured): rewrites the passage from the LD-338 context; its answer
  replaces the rule result only when it is valid.
A behaviour change that the rules cannot express gives a `review` suggestion without text.

LD-354 turns the findings of a drift report (LD-145) into the same kind of suggestion: each one
says which findings it resolves; stale line references get the entity's new line range.
"""
import difflib
import json
import re
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from .change_context import ChangeContextRequest, entity_context, build_change_index, endpoint_handlers
from .drift_affected import DocText, Hit, collect_docs, find_affected
from .drift_changes import analyze_pull_request
from .drift_models import (DocMatch, DocSource, DriftFinding, DriftReport, EntityChange,
                           EntityChangeType, FileChangeSummary, ParameterChangeKind, PullRequestInfo)
from .models import ContextDocument, now
from .renderer import LABELS
from .retrieval import Chunk, split_document

HTTP_VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


# ---------- API models ----------

class SuggestionStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    applied = "applied"
    conflict = "conflict"          # the documentation changed; `original` is no longer there


class SuggestionOperation(str, Enum):
    replace = "replace"            # `original` -> `proposed`
    delete = "delete"              # `proposed` is empty: the passage goes away
    insert = "insert"              # `proposed` = `original` + a new section after it
    review = "review"              # a person (or the AI) must write the text: `proposed` is None


class SuggestionTarget(BaseModel):
    source: DocSource              # document (saved, versioned) | repository (Markdown file)
    path: str                      # section path of a saved document, or the Markdown file
    document_id: Optional[str] = None
    title: Optional[str] = None
    version: Optional[int] = None  # version the suggestion was made against
    line_start: int                # passage lines inside the section / file (1-based)
    line_end: int


class SuggestionReview(BaseModel):
    decision: str                  # accept | reject
    reviewer: Optional[str] = None
    comment: Optional[str] = None
    edited: bool = False           # the reviewer changed the proposed text
    at: datetime = Field(default_factory=now)


class Suggestion(BaseModel):
    id: str
    batch_id: str
    source: str                    # code_change (LD-353) | drift (LD-354)
    status: SuggestionStatus = SuggestionStatus.pending
    operation: SuggestionOperation
    target: SuggestionTarget
    entities: List[str] = Field(default_factory=list)     # changed code entities it is about
    changes: List[str] = Field(default_factory=list)      # added | renamed | signature_changed ...
    finding_ids: List[str] = Field(default_factory=list)  # LD-354: drift findings it resolves
    reasons: List[str] = Field(default_factory=list)
    original: str
    proposed: Optional[str] = None
    diff: str = ""                 # unified diff original -> proposed
    method: str = "rule"           # rule | ai | none
    confidence: float = 0.0
    evidence: List[str] = Field(default_factory=list)     # "X1 shop/cart.py:10-15", ...
    review: Optional[SuggestionReview] = None
    applied_version: Optional[int] = None
    conflict: Optional[str] = None


class SuggestionBatch(BaseModel):
    id: str
    source: str
    created_at: datetime = Field(default_factory=now)
    repository: Optional[str] = None
    pull_request: Optional[PullRequestInfo] = None
    report_id: Optional[str] = None                       # LD-354
    suggestions: List[Suggestion] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class UpdateSuggestionRequest(ChangeContextRequest):
    output_language: str = Field(default="vi", pattern="^(vi|en)$")
    """Language of new sections written into repository Markdown (saved documents use their own)."""
    use_ai: bool = True            # ask the AI when one is configured


# ---------- edits on a passage ----------

def _word(name: str) -> re.Pattern:
    return re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")


def short(name: str) -> str:
    return name if " " in name else name.rsplit(".", 1)[-1]


def param_names(signature: Optional[str]) -> Optional[List[str]]:
    """'f(self, a: int, b=2) -> X' -> ['a', 'b']; None when there is no parameter list."""
    if not signature or "(" not in signature or ")" not in signature:
        return None
    inner = signature[signature.index("(") + 1:signature.rindex(")")]
    out, depth, cur = [], 0, ""
    for ch in inner + ",":
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        if ch == "," and depth == 0:
            name = re.split(r"[:=]", cur.strip(), maxsplit=1)[0].strip().lstrip("*")
            if name and name not in ("self", "cls"):
                # Java style "long id" -> "id"
                out.append(name.split()[-1])
            cur = ""
        else:
            cur += ch
    return out


@dataclass
class Edit:
    reason: str
    apply: Callable[[str], str]
    confidence: float
    operation: SuggestionOperation = SuggestionOperation.replace
    entity: str = ""
    change: str = ""


def rename_edit(old: str, new: str, terms: Sequence[str] = ()) -> Edit:
    """Rename an identifier, or an endpoint (old/new 'GET /path' keys)."""
    if " " in old:                                    # endpoint
        old_verb, old_path = old.split(" ", 1)
        new_verb, new_path = new.split(" ", 1)

        def run(text: str) -> str:
            variants = {old_path, *(t.split(" ", 1)[-1].strip("`") for t in terms)}
            for v in sorted(variants, key=len, reverse=True):
                if not v.startswith("/"):
                    continue
                text = re.sub(rf"\b{old_verb}(`?\s*`?){re.escape(v)}", lambda m: f"{new_verb}{m.group(1)}{new_path}", text)
                text = re.sub(rf"(?<![\w/]){re.escape(v)}(?![\w/{{:])", new_path, text)
            return text
        return Edit(f"`{old}` is now `{new}`", run, 0.9)

    o, n = short(old), short(new)
    return Edit(f"`{old}` was renamed to `{new}`", lambda t: _word(o).sub(n, t), 0.9)


def call_edit(name: str, new_signature: str) -> Optional[Edit]:
    """Rewrite documented calls `name(a, b)` with the new parameter names."""
    names = param_names(new_signature)
    if names is None:
        return None
    pat = re.compile(r"(?<![\w$])(" + re.escape(short(name)) + r")\(([^()]*)\)")

    def run(text: str) -> str:
        def repl(m: re.Match) -> str:
            typed = ":" in m.group(2)
            return f"{m.group(1)}({', '.join(names) if not typed else _typed_args(new_signature)})"
        return pat.sub(repl, text)
    return Edit(f"signature is now `{new_signature}`", run, 0.8)


def _typed_args(signature: str) -> str:
    inner = signature[signature.index("(") + 1:signature.rindex(")")]
    return ", ".join(p.strip() for p in inner.split(",") if p.strip() and p.strip().split(":")[0] not in ("self", "cls"))


_ROW = re.compile(r"^\s*\|\s*`?([\w$]+)`?\s*\|")


def _rows(lines: List[str]) -> List[int]:
    return [i for i, line in enumerate(lines) if _ROW.match(line)]


def param_table_edit(c: EntityChange) -> Optional[Edit]:
    """Remove / rename / retype / add rows of the parameter table of the entity's section."""
    pcs = c.parameter_changes
    if not pcs:
        return None
    new_types = _types(c.new_signature)

    def run(text: str) -> str:
        lines = text.split("\n")
        rows = _rows(lines)
        names = {_ROW.match(lines[i]).group(1): i for i in rows}
        if not names:
            return text
        drop = set()
        for p in pcs:
            if p.change == ParameterChangeKind.removed and p.name in names:
                drop.add(names[p.name])
            elif p.change == ParameterChangeKind.renamed and p.old_name in names:
                i = names[p.old_name]
                lines[i] = _word(p.old_name).sub(p.name, lines[i], count=1)
            elif p.change == ParameterChangeKind.type_changed and p.name in names and p.new_type:
                lines[names[p.name]] = _set_cell(lines[names[p.name]], 2, p.new_type)
        added = [p for p in pcs if p.change == ParameterChangeKind.added and p.name not in names]
        extra: List[str] = []
        if added:
            cells = lines[rows[-1]].strip().strip("|").split("|")
            for p in added:
                row = [f" `{p.name}` ", f" {p.new_type or new_types.get(p.name) or '-'} "] + \
                      [" - "] * (len(cells) - 2)
                extra.append("|" + "|".join(row[:len(cells)]) + "|")
        out = []
        for i, x in enumerate(lines):
            if i not in drop:
                out.append(x)
            if i == rows[-1]:
                out += extra
        return "\n".join(out)
    what = ", ".join(f"{p.change.value} `{p.name}`" for p in pcs)
    return Edit(f"parameters: {what}", run, 0.8)


def _types(signature: Optional[str]) -> Dict[str, str]:
    out = {}
    if signature and "(" in signature:
        for p in signature[signature.index("(") + 1:signature.rindex(")")].split(","):
            if ":" in p:
                n, t = p.split(":", 1)
                out[n.strip()] = t.split("=")[0].strip()
    return out


def _set_cell(row: str, index: int, value: str) -> str:
    parts = row.split("|")
    if len(parts) > index + 1:
        parts[index] = f" {value} "
    return "|".join(parts)


def return_type_edit(c: EntityChange) -> Optional[Edit]:
    if not (c.old_return_type and c.new_return_type) or c.old_return_type == c.new_return_type:
        return None
    labels = [LABELS[lang]["returns"] for lang in ("vi", "en")] + ["->"]

    def run(text: str) -> str:
        out = []
        for line in text.split("\n"):
            if any(lb in line for lb in labels):
                line = _word(c.old_return_type).sub(c.new_return_type, line)
            out.append(line)
        return "\n".join(out)
    return Edit(f"return type is now `{c.new_return_type}`", run, 0.8)


def docstring_edit(c: EntityChange) -> Optional[Edit]:
    old = (c.old_docstring or "").strip()
    new = (c.new_docstring or "").strip()
    if not old or not new or old == new:
        return None
    old_line, new_line = old.splitlines()[0].strip(), new.splitlines()[0].strip()

    def run(text: str) -> str:
        if old in text:
            return text.replace(old, new)
        return text.replace(old_line, new_line)
    return Edit("the docstring changed", run, 0.7)


def delete_edit(name: str, own_section: bool, terms: Sequence[str]) -> Edit:
    if own_section:
        return Edit(f"`{name}` was removed: delete its section", lambda t: "", 0.85,
                    SuggestionOperation.delete)
    pats = [_word(x) for x in {name, short(name), *terms} if x]

    def run(text: str) -> str:
        return "\n".join(line for line in text.split("\n") if not any(p.search(line) for p in pats))
    return Edit(f"`{name}` was removed: delete the lines that name it", run, 0.5)


def own_section(chunk: Optional[Chunk], name: str) -> bool:
    """The passage is the section of this entity (its heading names it)."""
    if chunk is None or not chunk.excerpt.lstrip().startswith("#"):
        return False
    return f"`{short(name)}`" in chunk.name or f"`{name}`" in chunk.name


def edits_for_change(c: EntityChange, matches: List[DocMatch], chunk: Optional[Chunk]) -> List[Edit]:
    terms = [m.term for m in matches]
    if c.change == EntityChangeType.removed:
        return [delete_edit(c.name, own_section(chunk, c.name), terms)]
    out: List[Optional[Edit]] = []
    if c.change == EntityChangeType.renamed and c.old_name:
        out.append(rename_edit(c.old_name, c.name, terms))
    if c.new_signature and c.kind != "endpoint":
        out.append(call_edit(c.name, c.new_signature))
    out += [param_table_edit(c), return_type_edit(c), docstring_edit(c)]
    return [e for e in out if e is not None]


# ---------- new entity: a section next to the others of its kind ----------

GROUP_KEYS = {"class": "Classes", "function": "Functions", "endpoint": "API Endpoints"}


def _heading_level(chunk: Chunk) -> int:
    m = re.match(r"\s*(#+)", chunk.excerpt)
    return len(m.group(1)) if m else 2


def new_section(c: EntityChange, level: int, lang: str, pr: Optional[PullRequestInfo]) -> str:
    L = LABELS.get(lang, LABELS["en"])
    title = f"{L['class']} `{c.name}`" if c.kind == "class" else f"`{short(c.name)}`"
    out = ["#" * level + " " + title, ""]
    if c.new_signature and c.kind != "endpoint":
        names = param_names(c.new_signature)
        sig = f"{short(c.name)}({', '.join(names)})" if names is not None else c.new_signature
        out += ["```", sig, "```", ""]
    where = f" (PR #{pr.number})" if pr else ""
    out.append(f"{L['no_desc']}{where}" if lang == "en" else f"{L['no_desc']} Mới thêm{where}, cần bổ sung mô tả.")
    types = _types(c.new_signature)
    names = param_names(c.new_signature) or []
    if names and c.kind != "endpoint":
        out += ["", f"**{L['params']}**", "",
                f"| {L['name']} | {L['type']} | {L['default']} | {L['desc']} |", "|---|---|---|---|"]
        out += [f"| `{n}` | {types.get(n, '-')} | - | - |" for n in names]
    return "\n".join(out)


def append_section(text: str, section: str) -> str:
    """`text` + a blank line + `section`, keeping the blank lines that ended `text`."""
    body = text.rstrip("\n")
    return body + "\n\n" + section + text[len(body):]


def insert_anchor(doc: DocText, c: EntityChange) -> Tuple[Optional[Chunk], int]:
    """Passage after which the new entity's section goes, and its heading level."""
    chunks = [ch for ch in split_document(ContextDocument(path=doc.path, content=doc.text))
              if ch.line_start]
    if not chunks:
        return None, 3

    def path_of(ch: Chunk) -> List[str]:
        return (ch.section or ch.name).split(" > ")

    if c.kind == "method" and "." in c.name:
        owner = f"`{c.name.rsplit('.', 1)[0]}`"
        group = [ch for ch in chunks if any(owner in part for part in path_of(ch))]
        head = next((ch for ch in group if owner in ch.name), None)
    else:
        key = GROUP_KEYS.get(c.kind)
        titles = {LABELS[lang][key] for lang in ("vi", "en")} if key else set()
        group = [ch for ch in chunks if titles & set(path_of(ch))]
        head = next((ch for ch in group if ch.name in titles), None)
    if group:
        return group[-1], (_heading_level(head) + 1) if head else 3
    return chunks[-1], 3


# ---------- passages ----------

@dataclass
class Passage:
    doc: DocText
    chunk: Optional[Chunk]
    start: int
    end: int
    edits: List[Edit] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    changes: List[str] = field(default_factory=list)
    finding_ids: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    context: List[str] = field(default_factory=list)     # LD-338 prompts, for the AI

    @property
    def original(self) -> str:
        return "\n".join(self.doc.lines[self.start - 1:self.end])

    def add(self, entity: str, change: str, edits: List[Edit], reasons: Sequence[str] = (),
            evidence: Sequence[str] = ()) -> None:
        if entity not in self.entities:
            self.entities.append(entity)
        if change not in self.changes:
            self.changes.append(change)
        known = {e.reason for e in self.edits}
        for e in edits:
            e.entity = e.entity or entity
            e.change = e.change or change
            if e.reason not in known:
                self.edits.append(e)
                known.add(e.reason)
        for r in reasons:                    # reasons that do not come from an edit
            if r not in self.reasons:
                self.reasons.append(r)
        for x in evidence:
            if x not in self.evidence:
                self.evidence.append(x)


def passage_of(doc: DocText, line: int) -> Tuple[Optional[Chunk], int, int]:
    chunks = split_document(ContextDocument(path=doc.path, content=doc.text))
    for ch in chunks:
        if ch.line_start and ch.line_end and ch.line_start <= line <= ch.line_end:
            return ch, ch.line_start, ch.line_end
    return None, line, line


class Passages:
    def __init__(self) -> None:
        self.items: "OrderedDict[Tuple, Passage]" = OrderedDict()

    def at(self, doc: DocText, line: int) -> Passage:
        ch, start, end = passage_of(doc, line)
        key = (doc.source.value, doc.document_id, doc.path, start)
        if key not in self.items:
            self.items[key] = Passage(doc, ch, start, end)
        return self.items[key]


# ---------- AI ----------

AI_SYSTEM = ("You update technical documentation after a code change. You receive the change "
             "(with its diff and related context) and one passage of the current documentation. "
             "Return only JSON: {\"proposed\": \"<the whole passage rewritten>\", \"reason\": "
             "\"<one sentence>\"}. Keep the passage's Markdown layout and language, change only "
             "what the code change makes wrong or incomplete, never invent behaviour.")


def ai_rewrite(client, p: Passage, rule_text: Optional[str]) -> Optional[Tuple[str, str]]:
    parts = ["\n\n".join(p.context), "", "Current documentation passage:", "```markdown", p.original, "```"]
    if rule_text is not None:
        parts += ["", "Mechanical update (names, signature, parameter table) already applied:",
                  "```markdown", rule_text, "```"]
    try:
        text = client.complete(AI_SYSTEM, [{"role": "user", "content": "\n".join(parts)}])
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        proposed = str(data.get("proposed", "")).strip("\n")
        if not proposed.strip() or proposed == p.original:
            return None
        return proposed, str(data.get("reason") or "rewritten by the AI from the code change")
    except Exception:          # API error or invalid answer: keep the rule result
        return None


# ---------- building suggestions ----------

def unified(original: str, proposed: Optional[str], path: str) -> str:
    if proposed is None:
        return ""
    return "\n".join(difflib.unified_diff(original.split("\n"), proposed.split("\n"),
                                          f"a/{path}", f"b/{path}", lineterm=""))


def to_suggestion(p: Passage, batch_id: str, source: str, client=None) -> Optional[Suggestion]:
    original = p.original
    text = original
    op = SuggestionOperation.replace
    conf = 1.0
    used: List[Edit] = []
    order = {SuggestionOperation.delete: 0, SuggestionOperation.replace: 1, SuggestionOperation.insert: 2}
    for e in sorted(p.edits, key=lambda e: order.get(e.operation, 1)):
        if e.operation == SuggestionOperation.delete:
            text, op, conf = "", SuggestionOperation.delete, e.confidence
            used.append(e)
            break
        new = e.apply(text)
        if new != text:
            used.append(e)
            conf = min(conf, e.confidence)
            if e.operation == SuggestionOperation.insert:
                op = SuggestionOperation.insert
        text = new
    reasons = list(p.reasons) + [e.reason for e in used if e.reason not in p.reasons]
    entities = list(dict.fromkeys(e.entity for e in used)) or list(p.entities)
    changes = list(dict.fromkeys(e.change for e in used)) or list(p.changes)
    proposed: Optional[str] = text
    method = "rule"
    if not used:                             # nothing a rule could change: a person must check
        proposed, op, conf, method = None, SuggestionOperation.review, 0.0, "none"
        if not reasons:
            reasons = [f"`{n}` changed; check this passage" for n in p.entities]
    if client is not None and op != SuggestionOperation.delete and p.context:
        got = ai_rewrite(client, p, proposed)
        if got is not None:
            proposed, why = got
            if op == SuggestionOperation.review:
                op = SuggestionOperation.replace
            method, conf = "ai", 0.75
            reasons.append(why)
    d = p.doc
    target = SuggestionTarget(source=d.source, path=d.path, document_id=d.document_id, title=d.title,
                              version=d.version, line_start=p.start, line_end=p.end)
    return Suggestion(id=uuid.uuid4().hex[:12], batch_id=batch_id, source=source, operation=op,
                      target=target, entities=entities, changes=changes, finding_ids=p.finding_ids,
                      reasons=reasons, original=original, proposed=proposed,
                      diff=unified(original, proposed, d.path), method=method,
                      confidence=round(conf, 2), evidence=p.evidence)


def _evidence(f: FileChangeSummary, c: EntityChange) -> List[str]:
    a, b = c.line_start, c.line_end
    loc = f.path + (f":{a}" + (f"-{b}" if b and b != a else "") if a else "")
    return [f"X1 {loc}"]


def change_passages(analysis, hits: List[Hit], contexts: Dict[int, str], lang_of: Callable[[DocText], str],
                    pr: Optional[PullRequestInfo]) -> Passages:
    out = Passages()
    for hit in hits:
        c, f = hit.target.change, hit.target.file
        if c is None:
            continue
        ctx = contexts.get(id(c))
        if c.change == EntityChangeType.added:
            if not hit.documents_file:
                continue
            anchor, level = insert_anchor(hit.doc, c)
            if anchor is None:
                continue
            p = out.at(hit.doc, anchor.line_start)
            section = new_section(c, level, lang_of(hit.doc), pr)
            edit = Edit(f"`{c.name}` was added: describe it", lambda t, s=section: append_section(t, s),
                        0.6, SuggestionOperation.insert)
            p.add(c.name, c.change.value, [edit], evidence=_evidence(f, c))
            if ctx and ctx not in p.context:
                p.context.append(ctx)
            continue
        by_passage: Dict[int, List[DocMatch]] = {}
        for m in hit.matches + hit.param_matches:
            p = out.at(hit.doc, m.line)
            by_passage.setdefault(id(p), []).append(m)
            edits = edits_for_change(c, by_passage[id(p)], p.chunk)
            reasons = []
            if c.change == EntityChangeType.behavior_changed and not any(
                    e.reason == "the docstring changed" for e in edits):
                reasons = [f"`{c.name}`: the behaviour changed ({'; '.join(c.details) or 'code body'}); "
                           "check that this passage is still true"]
            p.add(c.name, c.change.value, edits, reasons, _evidence(f, c))
            if ctx and ctx not in p.context:
                p.context.append(ctx)
    return out


def update_suggestions(req: UpdateSuggestionRequest, store, client=None) -> SuggestionBatch:
    analysis = analyze_pull_request(req.pull_request, req.files, req.repository)
    docs, warnings = collect_docs(store, req.document_ids, req.docs)
    _, hits = find_affected(analysis, docs)
    contexts: Dict[int, str] = {}
    if client is not None:          # LD-338 context is only needed by the AI
        index, handlers = build_change_index(req, docs), endpoint_handlers(req)
        by_path = {d.path: d for d in docs}
        for f in analysis.files:
            for c in f.entity_changes:
                own = [h for h in hits if h.target.change is c]
                h = handlers.get((f.path, c.name)) if c.kind == "endpoint" else None
                contexts[id(c)] = entity_context(index, f, c, own, by_path, req.k_code, req.k_docs, h).prompt

    def lang_of(d: DocText) -> str:
        if d.document_id:
            try:
                return store.get(d.document_id).output_language
            except Exception:
                pass
        return req.output_language

    batch = SuggestionBatch(id=uuid.uuid4().hex[:12], source="code_change", repository=req.repository,
                            pull_request=req.pull_request, warnings=warnings)
    passages = change_passages(analysis, hits, contexts, lang_of, req.pull_request)
    for p in passages.items.values():
        s = to_suggestion(p, batch.id, "code_change", client)
        if s is not None:
            batch.suggestions.append(s)
    if not docs:
        batch.warnings.append("No documentation was given: no saved document and no Markdown file in the request.")
    elif not batch.suggestions:
        batch.warnings.append("No documentation passage needs to change for this Pull Request.")
    suggestion_store.add(batch, {d.path: d.text for d in docs if d.source == DocSource.repository})
    return batch


def get_client(use_ai: bool = True):
    """The AI client when ANTHROPIC_API_KEY is set (tests replace this function)."""
    import os
    if not use_ai or not os.getenv("ANTHROPIC_API_KEY"):
        return None
    from .generator import AnthropicClient
    return AnthropicClient()


# ---------- LD-354: drift findings -> suggestions ----------

class DriftSuggestionRequest(BaseModel):
    docs: List[ContextDocument] = Field(default_factory=list)
    """Markdown files of the repository named by the report (their text is not kept in it)."""
    output_language: str = Field(default="vi", pattern="^(vi|en)$")
    use_ai: bool = True


SEMANTIC_REVIEW = {"status_codes_changed", "exceptions_changed", "values_changed",
                   "implementation_changed"}
_REF = re.compile(r"^(?P<path>.+?)(?P<sep>:|#L)(?P<a>\d+)(?:-L?(?P<b>\d+))?$")
_NOW = re.compile(r"now (?P<path>\S+?):(?P<a>\d+)(?:-(?P<b>\d+))?$")


def _ref_text(term: str, path: str, a: int, b: int) -> str:
    m = _REF.match(term)
    sep = m.group("sep") if m else ":"
    if sep == "#L":
        return f"{path}#L{a}" + (f"-L{b}" if b != a else "")
    return f"{path}:{a}" + (f"-{b}" if b != a else "")


def line_ref_edit(m: DocMatch, analysis) -> Optional[Edit]:
    """A stale `path:a-b` reference: its new place, from the note or from the entity that
    occupied exactly those lines before the change. An Edit that changes nothing means the
    reference is still right; None means its new place is unknown."""
    now_ = _NOW.search(m.note or "")
    if now_:
        path, a = now_.group("path"), int(now_.group("a"))
        b = int(now_.group("b") or a)
    else:
        ref = _REF.match(m.term)
        if not ref:
            return None
        a0, b0 = int(ref.group("a")), int(ref.group("b") or ref.group("a"))
        hit = next((c for f in analysis.files for c in f.entity_changes
                    if c.old_line_start == a0 and (c.old_line_end or c.old_line_start) == b0
                    and c.line_start), None)
        if hit is None:
            return None
        path, a, b = m.target, hit.line_start, hit.line_end or hit.line_start
    new = _ref_text(m.term, path, a, b)
    return Edit(f"`{m.term}` now points to `{new}`", lambda t, o=m.term, n=new: t.replace(o, n), 0.9)


def finding_doc(f: DriftFinding, store, files: Dict[str, str], warnings: List[str]) -> Optional[DocText]:
    d = f.document
    if d.source == DocSource.repository:
        text = files.get(d.path)
        if text is None:
            msg = f"{d.path}: the Markdown file is not in the request; its findings got no suggestion."
            if msg not in warnings:
                warnings.append(msg)
            return None
        return DocText(DocSource.repository, d.path, text)
    try:
        doc = store.get(d.document_id)
        v = store.version(d.document_id, d.version)
    except Exception:
        msg = f"Document '{d.document_id}' version {d.version} not found; its findings got no suggestion."
        if msg not in warnings:
            warnings.append(msg)
        return None
    for sec in v.sections if v.sections_match_content else []:
        if sec.path == d.path:
            return DocText(DocSource.document, sec.path, sec.markdown, doc.id, doc.title, v.number,
                           documents_file=sec.path)
    return DocText(DocSource.document, d.path, v.content, doc.id, doc.title, v.number)


def _change_of(report: DriftReport, f: DriftFinding) -> Optional[EntityChange]:
    for fs in report.analysis.files:
        if fs.path != f.file:
            continue
        for c in fs.entity_changes:
            if f.entity in (c.name, c.old_name):
                return c
    return None


def _diff_evidence(f: DriftFinding) -> List[str]:
    out = []
    for e in f.evidence:
        if e.kind.value == "code_diff" and e.path:
            a, b = e.line_start, e.line_end
            out.append(f"{e.id} {e.path}" + (f":{a}" + (f"-{b}" if b and b != a else "") if a else ""))
    return out[:1]


def drift_passages(report: DriftReport, store, files: Dict[str, str], lang_of,
                   warnings: List[str]) -> Passages:
    out = Passages()
    texts: Dict[Tuple, DocText] = {}
    for f in report.findings:
        key = (f.document.source.value, f.document.document_id, f.document.path)
        if key not in texts:
            doc = finding_doc(f, store, files, warnings)
            if doc is None:
                continue
            texts[key] = doc
        doc = texts[key]
        c = _change_of(report, f)
        why = f"{f.id}: {f.message}"
        if f.kind == "undocumented_entity" and c is not None:
            anchor, level = insert_anchor(doc, c)
            if anchor is None:
                continue
            p = out.at(doc, anchor.line_start)
            section = new_section(c, level, lang_of(doc), report.pull_request)
            p.add(c.name, f.kind, [Edit(f"`{c.name}` was added: describe it",
                                        lambda t, s=section: append_section(t, s), 0.6,
                                        SuggestionOperation.insert)], [why])
            p.finding_ids.append(f.id)
            continue
        groups: "OrderedDict[int, Tuple[Passage, List[DocMatch]]]" = OrderedDict()
        for m in f.document.matches:
            p = out.at(doc, m.line)
            groups.setdefault(id(p), (p, []))[1].append(m)
        for p, matches in groups.values():
            edits: List[Edit] = []
            reasons = [why] + ([f.suggestion] if f.kind in SEMANTIC_REVIEW and f.suggestion else [])
            evidence = _diff_evidence(f)
            if f.kind == "line_reference_stale":
                # the report's message lists every reference of the document: say only ours
                reasons, evidence = [], []
                for m in matches:
                    e = line_ref_edit(m, report.analysis)
                    if e is None:
                        reasons.append(f"{f.id}: `{m.term}`: {m.note}; check the reference")
                    elif e.apply(m.term) != m.term:
                        edits.append(e)
            elif f.kind in ("file_moved", "module_moved") and f.before and f.after:
                edits = [Edit(f"`{f.before}` is now `{f.after}`",
                              lambda t, o=f.before, n=f.after: _word(o).sub(n, t), 0.85)]
            elif f.kind in ("file_removed", "module_removed"):
                edits = [delete_edit(f.before or f.file, False, [m.term for m in matches])]
            elif f.kind not in SEMANTIC_REVIEW and c is not None:
                edits = edits_for_change(c, matches, p.chunk)
            p.add(f.entity or f.file, f.kind, edits, reasons, evidence)
            if f.id not in p.finding_ids:
                p.finding_ids.append(f.id)
    return out


def drift_suggestions(report: DriftReport, req: DriftSuggestionRequest, store, client=None) -> SuggestionBatch:
    warnings: List[str] = []
    files = {d.path: d.content for d in req.docs}

    def lang_of(d: DocText) -> str:
        if d.document_id:
            try:
                return store.get(d.document_id).output_language
            except Exception:
                pass
        return req.output_language

    batch = SuggestionBatch(id=uuid.uuid4().hex[:12], source="drift", repository=report.repository,
                            pull_request=report.pull_request, report_id=report.id, warnings=warnings)
    passages = drift_passages(report, store, files, lang_of, warnings)
    for p in passages.items.values():
        if client is not None and not p.context:
            p.context = [f"Drift findings for this passage: {'; '.join(p.reasons)}"]
        s = to_suggestion(p, batch.id, "drift", client)
        if s is not None:
            batch.suggestions.append(s)
    batch.warnings = list(warnings)       # the model keeps its own copy of the list
    if not report.findings:
        batch.warnings.append("The drift report has no finding: nothing to resolve.")
    covered = {i for s in batch.suggestions for i in s.finding_ids}
    missing = [f.id for f in report.findings if f.id not in covered]
    if missing and report.findings:
        batch.warnings.append(f"No suggestion for finding(s) {', '.join(missing)}.")
    suggestion_store.add(batch, files)
    return batch


# ---------- store (in memory, like drift reports) ----------

class SuggestionStore:
    def __init__(self, limit: int = 200) -> None:
        self._lock = threading.RLock()
        self.batches: "OrderedDict[str, SuggestionBatch]" = OrderedDict()
        self.files: Dict[str, Dict[str, str]] = {}      # batch id -> repository file -> text
        self.limit = limit

    def add(self, batch: SuggestionBatch, files: Dict[str, str]) -> SuggestionBatch:
        with self._lock:
            self.batches[batch.id] = batch
            self.files[batch.id] = files
            while len(self.batches) > self.limit:
                old, _ = self.batches.popitem(last=False)
                self.files.pop(old, None)
        return batch

    def batch(self, batch_id: str) -> Optional[SuggestionBatch]:
        return self.batches.get(batch_id)

    def get(self, suggestion_id: str) -> Optional[Suggestion]:
        for b in self.batches.values():
            for s in b.suggestions:
                if s.id == suggestion_id:
                    return s
        return None

    def list(self, batch_id: Optional[str] = None, status: Optional[str] = None,
             document_id: Optional[str] = None) -> List[Suggestion]:
        out = []
        for b in reversed(list(self.batches.values())):
            if batch_id and b.id != batch_id:
                continue
            out += [s for s in b.suggestions if (not status or s.status.value == status)
                    and (not document_id or s.target.document_id == document_id)]
        return out


suggestion_store = SuggestionStore()
